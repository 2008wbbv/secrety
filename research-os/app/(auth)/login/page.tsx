'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { BookOpen } from 'lucide-react'

type Mode = 'signin' | 'signup'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<Mode>('signin')
  const router = useRouter()
  const supabase = createClient()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)

    const { error: authError } =
      mode === 'signin'
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({ email, password })

    if (authError) {
      setError(authError.message)
      setLoading(false)
      return
    }

    router.push('/library')
    router.refresh()
  }

  const handleGoogle = async () => {
    const { error: authError } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    })
    if (authError) setError(authError.message)
  }

  return (
    <Card className="w-full max-w-md mx-4">
      <CardHeader className="space-y-1">
        <div className="flex items-center gap-2 mb-2">
          <BookOpen className="h-6 w-6" />
          <span className="font-bold text-lg">Research OS</span>
        </div>
        <CardTitle className="text-2xl">
          {mode === 'signin' ? 'Sign in' : 'Create account'}
        </CardTitle>
        <CardDescription>
          {mode === 'signin'
            ? 'Access your research library.'
            : 'Start building your research library.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              placeholder="8+ characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? 'Loading...' : mode === 'signin' ? 'Sign in' : 'Create account'}
          </Button>
        </form>

        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <span className="w-full border-t" />
          </div>
          <div className="relative flex justify-center text-xs uppercase">
            <span className="bg-card px-2 text-muted-foreground">Or</span>
          </div>
        </div>

        <Button variant="outline" className="w-full" onClick={handleGoogle} type="button">
          Continue with Google
        </Button>

        <p className="text-center text-sm text-muted-foreground">
          {mode === 'signin' ? "No account? " : 'Have an account? '}
          <button
            type="button"
            className="underline underline-offset-4 hover:text-primary"
            onClick={() => { setMode(mode === 'signin' ? 'signup' : 'signin'); setError(null) }}
          >
            {mode === 'signin' ? 'Sign up' : 'Sign in'}
          </button>
        </p>
      </CardContent>
    </Card>
  )
}
