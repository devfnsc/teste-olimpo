-- Evita que a história de uma persona seja reatribuída por acidente e que
-- conteúdo, planos, tarefas ou posts atravessem o limite da conta.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM story_arcs s
          JOIN accounts a ON a.id = s.account_id
         WHERE s.persona_id IS DISTINCT FROM a.persona_id
        UNION ALL
        SELECT 1
          FROM memories m
          JOIN accounts a ON a.id = m.account_id
         WHERE m.persona_id IS DISTINCT FROM a.persona_id
        UNION ALL
        SELECT 1
          FROM day_plans d
          JOIN accounts a ON a.id = d.account_id
         WHERE d.persona_id IS DISTINCT FROM a.persona_id
    ) THEN
        RAISE EXCEPTION
            'Há histórias, memórias ou planos cuja persona não corresponde à conta. Corrija os vínculos antes de aplicar 0012.';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM content_items c
          JOIN day_plans d ON d.id = c.day_plan_id
         WHERE c.account_id IS DISTINCT FROM d.account_id
        UNION ALL
        SELECT 1
          FROM tasks t
          JOIN content_items c ON c.id = t.content_item_id
         WHERE t.account_id IS DISTINCT FROM c.account_id
        UNION ALL
        SELECT 1
          FROM posts p
          JOIN content_items c ON c.id = p.content_item_id
         WHERE p.account_id IS DISTINCT FROM c.account_id
        UNION ALL
        SELECT 1
          FROM posts p
          JOIN tasks t ON t.id = p.task_id
         WHERE p.account_id IS DISTINCT FROM t.account_id
    ) THEN
        RAISE EXCEPTION
            'Há planos, tarefas ou posts ligados a outra conta. Corrija os vínculos antes de aplicar 0012.';
    END IF;
END;
$$;

-- O par único permite ao PostgreSQL validar a conta e a persona juntas.
ALTER TABLE accounts
    ADD CONSTRAINT uq_accounts_id_persona UNIQUE (id, persona_id);

ALTER TABLE story_arcs
    ADD CONSTRAINT fk_story_arcs_account_persona
    FOREIGN KEY (account_id, persona_id)
    REFERENCES accounts (id, persona_id)
    ON DELETE CASCADE;

ALTER TABLE memories
    ADD CONSTRAINT fk_memories_account_persona
    FOREIGN KEY (account_id, persona_id)
    REFERENCES accounts (id, persona_id)
    ON DELETE CASCADE;

ALTER TABLE day_plans
    ADD CONSTRAINT uq_day_plans_id_account UNIQUE (id, account_id),
    ADD CONSTRAINT fk_day_plans_account_persona
    FOREIGN KEY (account_id, persona_id)
    REFERENCES accounts (id, persona_id)
    ON DELETE CASCADE;

ALTER TABLE content_items
    ADD CONSTRAINT uq_content_items_id_account UNIQUE (id, account_id),
    ADD CONSTRAINT fk_content_items_day_plan_account
    FOREIGN KEY (day_plan_id, account_id)
    REFERENCES day_plans (id, account_id)
    ON DELETE SET NULL (day_plan_id);

ALTER TABLE tasks
    ADD CONSTRAINT uq_tasks_id_account UNIQUE (id, account_id),
    ADD CONSTRAINT ck_tasks_content_requires_account
    CHECK (content_item_id IS NULL OR account_id IS NOT NULL),
    ADD CONSTRAINT fk_tasks_content_item_account
    FOREIGN KEY (content_item_id, account_id)
    REFERENCES content_items (id, account_id)
    ON DELETE SET NULL (content_item_id);

ALTER TABLE posts
    ADD CONSTRAINT fk_posts_content_item_account
    FOREIGN KEY (content_item_id, account_id)
    REFERENCES content_items (id, account_id)
    ON DELETE SET NULL (content_item_id),
    ADD CONSTRAINT fk_posts_task_account
    FOREIGN KEY (task_id, account_id)
    REFERENCES tasks (id, account_id)
    ON DELETE SET NULL (task_id);

-- Reatribuir uma conta com histórico deixa as narrativas ligadas à identidade
-- errada. A API faz uma pré-verificação amigável; este trigger também protege
-- gravações diretas e operações concorrentes.
CREATE OR REPLACE FUNCTION prevent_persona_rebind_with_history()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.persona_id IS DISTINCT FROM OLD.persona_id AND (
        EXISTS (SELECT 1 FROM story_arcs WHERE account_id = OLD.id)
        OR EXISTS (SELECT 1 FROM memories WHERE account_id = OLD.id)
        OR EXISTS (SELECT 1 FROM day_plans WHERE account_id = OLD.id)
    ) THEN
        RAISE EXCEPTION
            'A conta tem história, memória ou plano vinculado; reatribua esses dados antes de trocar a persona.'
            USING ERRCODE = '23514', CONSTRAINT = 'accounts_persona_history_locked';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_accounts_persona_history_locked
    BEFORE UPDATE OF persona_id ON accounts
    FOR EACH ROW EXECUTE FUNCTION prevent_persona_rebind_with_history();

