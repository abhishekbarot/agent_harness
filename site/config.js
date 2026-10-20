// Workspace configuration. Leave supabaseUrl empty and the workspace saves
// everything in the student's browser. Fill in both values (Supabase dashboard
// -> Project Settings -> API) and students can sign in to keep their work
// across devices. The anon key is meant to be public: the database's
// row-level security rules (supabase/schema.sql) are what protect each
// student's data.
window.WORKSPACE_CONFIG = {
  supabaseUrl: "",
  supabaseAnonKey: "",
  // Sign-in providers to offer. Each must also be enabled in Supabase
  // (Authentication -> Providers).
  providers: ["github", "google"],
};
