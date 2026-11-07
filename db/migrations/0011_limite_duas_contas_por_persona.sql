-- Uma persona pode representar até duas contas (por exemplo, duas
-- plataformas), sem permitir vínculos ilimitados por engano.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM accounts
         WHERE persona_id IS NOT NULL
         GROUP BY persona_id
        HAVING count(*) > 2
    ) THEN
        RAISE EXCEPTION
            'Há personas com mais de duas contas. Corrija os vínculos antes de aplicar 0011.';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION enforce_two_accounts_per_persona()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    linked_count integer;
BEGIN
    IF NEW.persona_id IS NULL THEN
        RETURN NEW;
    END IF;

    -- Serializa alterações simultâneas para a mesma persona, inclusive
    -- gravações que não passam pelos endpoints da API.
    PERFORM pg_advisory_xact_lock(hashtextextended(NEW.persona_id::text, 0));

    SELECT count(*) INTO linked_count
      FROM accounts
     WHERE persona_id = NEW.persona_id
       AND id IS DISTINCT FROM NEW.id;

    IF linked_count >= 2 THEN
        RAISE EXCEPTION 'uma persona pode ter no máximo duas contas vinculadas'
            USING ERRCODE = '23514', CONSTRAINT = 'accounts_persona_max_two';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_accounts_two_per_persona
    BEFORE INSERT OR UPDATE OF persona_id ON accounts
    FOR EACH ROW EXECUTE FUNCTION enforce_two_accounts_per_persona();

