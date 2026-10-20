// Where a student's work is kept: finished exercises, code drafts, the days
// they practised, and the exercise they were last on.
//
// Two modes behind one API:
//   - browser: everything in localStorage. Used when no Supabase project is
//     configured, and while a student is signed out.
//   - account: a signed-in student's data lives in Supabase and follows them
//     across devices. The browser copy is kept as a cache, so the sheet page
//     (which only reads the browser copy) shows the same ticks.
//
// Storage can throw or come back empty (private windows, blocked site data),
// so every browser read and write is guarded and the workspace still works for
// the current visit without it.

(function () {
  "use strict";

  const KEYS = {
    progress: "agent-sheet:progress:v1", // shared with the sheet page
    drafts: "agent-sheet:drafts:v1",
    activity: "agent-sheet:activity:v1",
    last: "agent-sheet:last:v1",
  };
  const SUPABASE_SDK = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/dist/umd/supabase.min.js";
  // Where to return after the sign-in round trip (e.g. "#ex-3-1").
  const RETURN_KEY = "agent-sheet:return-to";

  const local = {
    get(key, fallback) {
      try {
        const raw = window.localStorage.getItem(key);
        return raw === null ? fallback : JSON.parse(raw);
      } catch (_) {
        return fallback;
      }
    },
    set(key, value) {
      try {
        window.localStorage.setItem(key, JSON.stringify(value));
      } catch (_) {
        /* kept in memory for this visit */
      }
    },
    // Change one entry against the stored copy, not this page's snapshot of
    // it. With two tabs open, writing the whole snapshot back would undo
    // whatever the other tab saved in the meantime.
    update(key, fallback, change) {
      local.set(key, change(local.get(key, fallback)));
    },
  };
  const withItem = (list, item) => (Array.isArray(list) ? [...new Set([...list, item])] : [item]);

  // Local calendar day, e.g. "2026-10-20". Streaks follow the student's own
  // midnight, not UTC.
  function today(date = new Date()) {
    const pad = (n) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  }

  // Consecutive practice days ending today, or yesterday if the student hasn't
  // practised yet today (the streak isn't broken until the day is over).
  function streak(days, now = new Date()) {
    const set = new Set(days);
    const cursor = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    if (!set.has(today(cursor))) cursor.setDate(cursor.getDate() - 1);
    let count = 0;
    while (set.has(today(cursor))) {
      count += 1;
      cursor.setDate(cursor.getDate() - 1);
    }
    return count;
  }

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = src;
      script.onload = resolve;
      script.onerror = () => reject(new Error(`could not load ${src}`));
      document.head.append(script);
    });
  }

  function userFrom(session) {
    if (!session || !session.user) return null;
    const meta = session.user.user_metadata || {};
    return {
      id: session.user.id,
      name: meta.full_name || meta.name || meta.user_name || session.user.email || "Student",
      email: session.user.email || "",
      avatarUrl: meta.avatar_url || "",
    };
  }

  class Store {
    constructor(config) {
      this.config = config || {};
      this.client = null;
      this.user = null;
      this.error = "";
      this.listeners = new Set();
      // In-memory state; the browser copy is loaded once and written through.
      this.state = {
        progress: new Set(local.get(KEYS.progress, [])),
        drafts: { ...local.get(KEYS.drafts, {}) },
        activity: new Set(local.get(KEYS.activity, [])),
      };
    }

    get accountsEnabled() {
      return Boolean(this.config.supabaseUrl && this.config.supabaseAnonKey);
    }

    get mode() {
      return this.user ? "account" : "browser";
    }

    onChange(listener) {
      this.listeners.add(listener);
      return () => this.listeners.delete(listener);
    }

    emit() {
      for (const listener of this.listeners) listener(this);
    }

    // Report a failed account write without losing the work: the browser copy
    // was already saved.
    fail(action, error) {
      this.error = `Couldn't ${action} in your account (${error.message || error}). It's saved in this browser for now.`;
      this.emit();
    }

    async init() {
      if (!this.accountsEnabled) return this;
      try {
        if (!window.supabase) await loadScript(SUPABASE_SDK);
        // PKCE returns the sign-in result as ?code=... rather than in the URL
        // fragment, which the workspace uses for navigation (#ex-3-1).
        this.client = window.supabase.createClient(this.config.supabaseUrl, this.config.supabaseAnonKey, {
          auth: { flowType: "pkce", persistSession: true, detectSessionInUrl: true },
        });
        const { data } = await this.client.auth.getSession();
        this.restoreReturnHash();
        await this.adopt(data && data.session);
        this.client.auth.onAuthStateChange((_event, session) => {
          const next = userFrom(session);
          if ((next && next.id) !== (this.user && this.user.id)) this.adopt(session);
        });
      } catch (error) {
        this.client = null;
        this.error = `Sign-in is unavailable right now (${error.message}). Your work is saved in this browser.`;
      }
      return this;
    }

    // Switch to a signed-in (or signed-out) user. On sign-in, anything done
    // in this browser while signed out is added to the account, then the
    // account's data becomes the working copy.
    async adopt(session) {
      this.user = userFrom(session);
      if (this.user) {
        await this.mergeLocalIntoAccount();
        await this.pull();
      }
      this.emit();
    }

    restoreReturnHash() {
      try {
        const hash = window.sessionStorage.getItem(RETURN_KEY);
        window.sessionStorage.removeItem(RETURN_KEY);
        if (hash && !window.location.hash) window.history.replaceState(null, "", hash);
      } catch (_) {
        /* nothing to restore */
      }
    }

    async pull() {
      const [progress, drafts, activity] = await Promise.all([
        this.client.from("progress").select("item_id"),
        this.client.from("drafts").select("item_id,code"),
        this.client.from("activity").select("day"),
      ]);
      const failed = [progress, drafts, activity].find((r) => r.error);
      if (failed) {
        this.fail("load your work", failed.error);
        return;
      }
      this.state.progress = new Set(progress.data.map((r) => r.item_id));
      this.state.drafts = Object.fromEntries(drafts.data.map((r) => [r.item_id, r.code]));
      this.state.activity = new Set(activity.data.map((r) => r.day));
      this.saveLocal();
    }

    async mergeLocalIntoAccount() {
      const uid = this.user.id;
      const progress = [...this.state.progress].map((item_id) => ({ user_id: uid, item_id }));
      const activity = [...this.state.activity].map((day) => ({ user_id: uid, day }));
      const writes = [];
      if (progress.length) {
        writes.push(this.client.from("progress").upsert(progress, { onConflict: "user_id,item_id", ignoreDuplicates: true }));
      }
      if (activity.length) {
        writes.push(this.client.from("activity").upsert(activity, { onConflict: "user_id,day", ignoreDuplicates: true }));
      }
      // Drafts only fill gaps: code already in the account is never
      // overwritten by an older copy from this browser.
      const drafts = Object.entries(this.state.drafts).map(([item_id, code]) => ({ user_id: uid, item_id, code }));
      if (drafts.length) {
        writes.push(this.client.from("drafts").upsert(drafts, { onConflict: "user_id,item_id", ignoreDuplicates: true }));
      }
      const results = await Promise.all(writes);
      const failed = results.find((r) => r && r.error);
      if (failed) this.fail("add this browser's work to your account", failed.error);
    }

    saveLocal() {
      local.set(KEYS.progress, [...this.state.progress]);
      local.set(KEYS.drafts, this.state.drafts);
      local.set(KEYS.activity, [...this.state.activity]);
    }

    // The provider sends the student back to the bare page address (the one
    // registered in Supabase); the exercise they were on is restored after.
    async signIn(provider) {
      if (!this.client) return;
      try {
        window.sessionStorage.setItem(RETURN_KEY, window.location.hash);
      } catch (_) {
        /* they land on the dashboard instead */
      }
      const redirectTo = window.location.origin + window.location.pathname;
      const { error } = await this.client.auth.signInWithOAuth({ provider, options: { redirectTo } });
      if (error) {
        this.error = `Couldn't start sign-in (${error.message}).`;
        this.emit();
      }
    }

    // Signing out also clears this browser's copy: on a shared lab computer
    // the next person must not see the previous student's code. Nothing is
    // lost, because the account already holds it.
    async signOut() {
      if (!this.client) return;
      await this.client.auth.signOut();
      this.state = { progress: new Set(), drafts: {}, activity: new Set() };
      this.saveLocal();
      local.set(KEYS.last, null);
      await this.adopt(null);
    }

    // -- reads ---------------------------------------------------------------

    isDone(id) {
      return this.state.progress.has(id);
    }

    doneIds() {
      return new Set(this.state.progress);
    }

    draft(id) {
      return Object.prototype.hasOwnProperty.call(this.state.drafts, id) ? this.state.drafts[id] : null;
    }

    streak(now) {
      return streak(this.state.activity, now);
    }

    lastExercise() {
      return local.get(KEYS.last, null);
    }

    // -- writes: browser first, then the account -----------------------------

    async markDone(id) {
      if (this.state.progress.has(id)) return;
      this.state.progress.add(id);
      local.update(KEYS.progress, [], (list) => withItem(list, id));
      this.emit();
      if (!this.user) return;
      const { error } = await this.client
        .from("progress")
        .upsert({ user_id: this.user.id, item_id: id }, { onConflict: "user_id,item_id", ignoreDuplicates: true });
      if (error) this.fail("save your progress", error);
    }

    async saveDraft(id, code) {
      this.state.drafts[id] = code;
      local.update(KEYS.drafts, {}, (drafts) => ({ ...drafts, [id]: code }));
      if (!this.user) return;
      const { error } = await this.client
        .from("drafts")
        .upsert(
          { user_id: this.user.id, item_id: id, code, updated_at: new Date().toISOString() },
          { onConflict: "user_id,item_id" },
        );
      if (error) this.fail("save your code", error);
    }

    async clearDraft(id) {
      delete this.state.drafts[id];
      local.update(KEYS.drafts, {}, (drafts) => {
        const next = { ...drafts };
        delete next[id];
        return next;
      });
      if (!this.user) return;
      // The database rules already limit this to the student's own rows;
      // the user_id filter keeps it that way even if a rule is misconfigured.
      const { error } = await this.client.from("drafts").delete().eq("user_id", this.user.id).eq("item_id", id);
      if (error) this.fail("reset your code", error);
    }

    async recordActivity(now) {
      const day = today(now);
      if (this.state.activity.has(day)) return;
      this.state.activity.add(day);
      local.update(KEYS.activity, [], (list) => withItem(list, day));
      this.emit();
      if (!this.user) return;
      const { error } = await this.client
        .from("activity")
        .upsert({ user_id: this.user.id, day }, { onConflict: "user_id,day", ignoreDuplicates: true });
      if (error) this.fail("save today's practice", error);
    }

    setLastExercise(id) {
      local.set(KEYS.last, id);
    }
  }

  window.WorkspaceStore = {
    create: (config) => new Store(config).init(),
    streak,
    today,
    KEYS,
  };
})();
