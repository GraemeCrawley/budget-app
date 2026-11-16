-- 2 -> 3: an override copied from an owner merchant rule remembers that rule's merchant key, so a later
-- merchant-wide correction can reach it. NULL = the owner set this override by hand.
ALTER TABLE overrides ADD COLUMN carried_key TEXT;
