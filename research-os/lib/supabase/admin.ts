import { createClient } from '@supabase/supabase-js'

// Intentionally untyped to avoid requiring generated Database types in background jobs.
// Callers validate shapes using domain types in types/index.ts.
// biome-ignore lint: intentional any
let adminClient: any = null // eslint-disable-line

// biome-ignore lint: intentional any
export function createAdminClient(): any { // eslint-disable-line
  if (!adminClient) {
    adminClient = createClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.SUPABASE_SERVICE_ROLE_KEY!,
      { auth: { persistSession: false } }
    )
  }
  return adminClient
}
