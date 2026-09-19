-- =================================================================================
-- LexAI Chat History Schema
-- 
-- INSTRUCTIONS:
-- 1. Go to your Supabase Dashboard: https://supabase.com/dashboard
-- 2. Open your project
-- 3. Click "SQL Editor" on the left sidebar
-- 4. Click "New Query"
-- 5. Paste this entire file into the editor and click "Run"
-- =================================================================================

-- 1. Create chat_sessions table
CREATE TABLE IF NOT EXISTS public.chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'New Chat',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Create chat_messages table
CREATE TABLE IF NOT EXISTS public.chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Indexes for fast retrieval
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON public.chat_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON public.chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON public.chat_messages(created_at);

-- 4. Enable Row Level Security (RLS)
ALTER TABLE public.chat_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;

-- 5. RLS Policies for chat_sessions
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can view their own sessions') THEN
        CREATE POLICY "Users can view their own sessions" ON public.chat_sessions
            FOR SELECT USING (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can insert their own sessions') THEN
        CREATE POLICY "Users can insert their own sessions" ON public.chat_sessions
            FOR INSERT WITH CHECK (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can update their own sessions') THEN
        CREATE POLICY "Users can update their own sessions" ON public.chat_sessions
            FOR UPDATE USING (auth.uid() = user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can delete their own sessions') THEN
        CREATE POLICY "Users can delete their own sessions" ON public.chat_sessions
            FOR DELETE USING (auth.uid() = user_id);
    END IF;
END $$;

-- 6. RLS Policies for chat_messages
-- Messages are secured via the session_id owner
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can view messages of their sessions') THEN
        CREATE POLICY "Users can view messages of their sessions" ON public.chat_messages
            FOR SELECT USING (
                EXISTS (
                    SELECT 1 FROM public.chat_sessions
                    WHERE chat_sessions.id = chat_messages.session_id
                    AND chat_sessions.user_id = auth.uid()
                )
            );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can insert messages to their sessions') THEN
        CREATE POLICY "Users can insert messages to their sessions" ON public.chat_messages
            FOR INSERT WITH CHECK (
                EXISTS (
                    SELECT 1 FROM public.chat_sessions
                    WHERE chat_sessions.id = chat_messages.session_id
                    AND chat_sessions.user_id = auth.uid()
                )
            );
    END IF;
END $$;
