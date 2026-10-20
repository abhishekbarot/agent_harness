# Student accounts (Supabase)

The workspace works without accounts: each student's code and progress are saved in their own browser. Connect a Supabase project and students can sign in with GitHub or Google, so their work follows them to any device.

Supabase provides the sign-in and the database. The site stays static on GitHub Pages and talks to Supabase directly from the browser.

## Set up (about 15 minutes)

1. **Create a project** at [supabase.com](https://supabase.com). The free tier is enough to start.

2. **Create the tables.** In the project, open **SQL Editor**, paste [`schema.sql`](schema.sql), and run it. It creates three tables (`progress`, `drafts`, `activity`) and turns on row-level security, so each student can only read and write their own rows.

3. **Set the site address.** Under **Authentication → URL Configuration**:
   - **Site URL:** `https://abhishekbarot.github.io/agent_harness/`
   - **Redirect URLs:** add `https://abhishekbarot.github.io/agent_harness/workspace.html`, and `http://localhost:8000/workspace.html` if you want sign-in to work when previewing locally.

4. **Turn on sign-in providers.** Under **Authentication → Providers**:
   - **GitHub:** create an OAuth app at GitHub → Settings → Developer settings → OAuth Apps. Use the callback URL Supabase shows you, then paste the app's client ID and secret into Supabase.
   - **Google:** create an OAuth client in Google Cloud Console (APIs & Services → Credentials), with the callback URL Supabase shows you, then paste its client ID and secret into Supabase.

   To offer only one, list just that provider in `providers` in `site/config.js`.

5. **Connect the site.** Under **Project Settings → API**, copy the **Project URL** and the **anon public** key into `site/config.js`:

   ```js
   window.WORKSPACE_CONFIG = {
     supabaseUrl: "https://YOUR-PROJECT.supabase.co",
     supabaseAnonKey: "eyJ...",
     providers: ["github", "google"],
   };
   ```

   Commit and push. The site redeploys with sign-in turned on.

## Is the anon key safe in the page?

Yes. It's designed to be public, and anyone can read it in the page source. What protects student data is row-level security in `schema.sql`. Every table allows only `auth.uid() = user_id`, so a signed-in student can reach their own rows and nothing else, and a signed-out visitor can reach nothing.

**Never** put the `service_role` key in the site. It bypasses row-level security.

## What happens to work done before signing in

When a student signs in, anything they did in that browser while signed out is added to their account:
- Finished exercises are added.
- Drafts fill gaps only. A draft already in the account is never overwritten by an older copy from the browser.

When they sign out, the browser's copy is cleared, so the next person on a shared computer doesn't see their code. Nothing is lost, because it's in their account.

## Student data

The tables hold, per student: which exercises they finished, their latest code for each exercise, and the dates they practised. Supabase's auth tables hold their name, email and avatar from GitHub or Google. If a student asks you to delete their data, delete their user under **Authentication → Users**. The three tables are set to `on delete cascade`, so their rows go with it.
