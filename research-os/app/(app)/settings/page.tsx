import { createClient } from '@/lib/supabase/server'
import { Header } from '@/components/shell/header'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export default async function SettingsPage() {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()

  return (
    <div className="flex flex-col h-full">
      <Header title="Settings" />
      <div className="flex-1 overflow-auto p-6 max-w-2xl">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Account</CardTitle>
              <CardDescription>Your account details.</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">{user?.email}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>About</CardTitle>
              <CardDescription>Research OS v0.1.0</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Personal research workspace. Ingest papers, search your library, and get AI-assisted answers grounded in your research.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
