-- ============================================================================
-- 016: Add display_name to agent_user_profiles + relax NOT NULL constraints
-- Enables storing user name from chat (without DMS/onboarding) for greeting
-- personalization across conversations.
-- ============================================================================

-- 1. Add display_name column (name from chat, separate from DMS fio)
ALTER TABLE agent_user_profiles
  ADD COLUMN IF NOT EXISTS display_name TEXT;

-- 2. Relax NOT NULL on phone, client_type, user_role
--    Guest users may not have phone/type yet — profile grows progressively.
ALTER TABLE agent_user_profiles
  ALTER COLUMN phone DROP NOT NULL;

ALTER TABLE agent_user_profiles
  ALTER COLUMN client_type DROP NOT NULL;

ALTER TABLE agent_user_profiles
  ALTER COLUMN user_role DROP NOT NULL;

-- 3. Drop CHECK constraints that block NULL values, recreate with NULL-safe versions
ALTER TABLE agent_user_profiles
  DROP CONSTRAINT IF EXISTS agent_user_profiles_client_type_check;
ALTER TABLE agent_user_profiles
  ADD CONSTRAINT agent_user_profiles_client_type_check
    CHECK (client_type IS NULL OR client_type IN ('existing', 'new'));

ALTER TABLE agent_user_profiles
  DROP CONSTRAINT IF EXISTS agent_user_profiles_user_role_check;
ALTER TABLE agent_user_profiles
  ADD CONSTRAINT agent_user_profiles_user_role_check
    CHECK (user_role IS NULL OR user_role IN ('parent', 'student'));

ALTER TABLE agent_user_profiles
  DROP CONSTRAINT IF EXISTS agent_user_profiles_verification_status_check;
ALTER TABLE agent_user_profiles
  ADD CONSTRAINT agent_user_profiles_verification_status_check
    CHECK (verification_status IS NULL OR verification_status IN ('pending', 'found', 'not_found', 'unexpected_found', 'new_lead'));
