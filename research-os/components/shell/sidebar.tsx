'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { BookOpen, MessageCircle, FileText, FolderOpen, Settings, LogOut } from 'lucide-react'
import { cn } from '@/lib/utils'
import { createClient } from '@/lib/supabase/client'
import { Button } from '@/components/ui/button'

const navItems = [
  { href: '/library', icon: BookOpen, label: 'Library' },
  { href: '/assistant', icon: MessageCircle, label: 'Assistant' },
  { href: '/notes', icon: FileText, label: 'Notes' },
  { href: '/collections', icon: FolderOpen, label: 'Collections' },
]

export function Sidebar() {
  const pathname = usePathname()
  const router = useRouter()
  const supabase = createClient()

  const handleSignOut = async () => {
    await supabase.auth.signOut()
    router.push('/login')
    router.refresh()
  }

  return (
    <aside className="flex h-full w-56 flex-col border-r bg-background">
      <div className="flex h-14 items-center gap-2 border-b px-4">
        <BookOpen className="h-5 w-5" />
        <span className="font-semibold">Research OS</span>
      </div>

      <nav className="flex-1 space-y-1 p-2">
        {navItems.map(({ href, icon: Icon, label }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
              pathname.startsWith(href)
                ? 'bg-accent text-accent-foreground'
                : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </Link>
        ))}
      </nav>

      <div className="border-t p-2 space-y-1">
        <Link
          href="/settings"
          className={cn(
            'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
            pathname.startsWith('/settings')
              ? 'bg-accent text-accent-foreground'
              : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
          )}
        >
          <Settings className="h-4 w-4" />
          Settings
        </Link>
        <Button
          variant="ghost"
          className="w-full justify-start gap-3 text-muted-foreground"
          onClick={handleSignOut}
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </Button>
      </div>
    </aside>
  )
}
