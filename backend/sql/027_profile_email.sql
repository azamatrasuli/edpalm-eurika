-- Migration 027: Add email column to agent_user_profiles
-- Email from portal registration / auto-enrich

ALTER TABLE agent_user_profiles
    ADD COLUMN IF NOT EXISTS email TEXT;

COMMENT ON COLUMN agent_user_profiles.email IS 'Email from portal or DMS';
