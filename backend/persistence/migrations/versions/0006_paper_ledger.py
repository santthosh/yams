"""Atomic paper ledger, immutable source envelopes and rebuildable projections."""

from alembic import op

revision = "0006_paper_ledger"
down_revision = "0005a_experiment_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE paper_portfolio (
            id UUID PRIMARY KEY,
            workspace_id UUID NOT NULL REFERENCES local_workspace(id) ON DELETE RESTRICT,
            name VARCHAR(120) NOT NULL CHECK (length(name)>0),
            currency VARCHAR(3) NOT NULL CHECK (currency='USD'),
            source_mode VARCHAR(32) NOT NULL CHECK (source_mode IN ('synthetic_fixture',
                'research_market_data')),
            strategy_version_id UUID NOT NULL REFERENCES strategy_version(id) ON DELETE RESTRICT,
            opening_cash_usd NUMERIC(24, 2) NOT NULL CHECK (opening_cash_usd>0 AND
                opening_cash_usd<1e22),
            opening_event_id UUID NOT NULL UNIQUE,
            opening_sha256 VARCHAR(64) NOT NULL CHECK (opening_sha256 ~ '^[0-9a-f]{64}$'),
            cash_usd NUMERIC(24, 2) NOT NULL CHECK (cash_usd>=0 AND cash_usd<1e22),
            revision BIGINT NOT NULL CHECK (revision>=0),
            last_sequence BIGINT NOT NULL CHECK (last_sequence>=0),
            status VARCHAR(24) NOT NULL CHECK (status IN ('active', 'paused', 'closed')),
            reconciliation_failed BOOLEAN NOT NULL,
            state_metadata JSONB NOT NULL CHECK (jsonb_typeof(state_metadata)='object'),
            created_at TIMESTAMPTZ NOT NULL
        );
        CREATE TABLE recommendation (
            id UUID PRIMARY KEY,
            portfolio_id UUID NOT NULL REFERENCES paper_portfolio(id) ON DELETE RESTRICT,
            strategy_version_id UUID NOT NULL REFERENCES strategy_version(id) ON DELETE RESTRICT,
            snapshot_id UUID NOT NULL REFERENCES dataset_snapshot(id) ON DELETE RESTRICT,
            as_of_session DATE NOT NULL,
            decision_cutoff TIMESTAMPTZ NOT NULL,
            portfolio_revision BIGINT NOT NULL CHECK (portfolio_revision>=0),
            source_mode VARCHAR(32) NOT NULL CHECK (source_mode IN ('synthetic_fixture',
                'research_market_data')),
            content JSONB NOT NULL CHECK (jsonb_typeof(content)='object'),
            content_sha256 VARCHAR(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
            disposition VARCHAR(24) NOT NULL CHECK (disposition IN ('ready', 'applied',
                'dismissed', 'expired')),
            created_at TIMESTAMPTZ NOT NULL,
            UNIQUE (id, portfolio_id, strategy_version_id, snapshot_id)
        );
        CREATE TABLE paper_order_batch (
            id UUID PRIMARY KEY,
            portfolio_id UUID NOT NULL REFERENCES paper_portfolio(id) ON DELETE RESTRICT,
            recommendation_id UUID NOT NULL UNIQUE REFERENCES recommendation(id) ON DELETE RESTRICT,
            strategy_version_id UUID NOT NULL REFERENCES strategy_version(id) ON DELETE RESTRICT,
            snapshot_id UUID NOT NULL REFERENCES dataset_snapshot(id) ON DELETE RESTRICT,
            snapshot_sha256 VARCHAR(64) NOT NULL CHECK (snapshot_sha256 ~ '^[0-9a-f]{64}$'),
            calendar_sha256 VARCHAR(64) NOT NULL CHECK (calendar_sha256 ~ '^[0-9a-f]{64}$'),
            approved_revision BIGINT NOT NULL CHECK (approved_revision>=0),
            approved_at TIMESTAMPTZ NOT NULL,
            decision_cutoff TIMESTAMPTZ NOT NULL,
            eligible_open_at TIMESTAMPTZ NOT NULL CHECK (eligible_open_at>approved_at AND
                eligible_open_at>decision_cutoff),
            idempotency_key UUID NOT NULL,
            request_sha256 VARCHAR(64) NOT NULL CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
            intent JSONB NOT NULL CHECK (jsonb_typeof(intent)='object'),
            intent_sha256 VARCHAR(64) NOT NULL CHECK (intent_sha256 ~ '^[0-9a-f]{64}$'),
            context JSONB NOT NULL CHECK (jsonb_typeof(context)='object'),
            policy JSONB NOT NULL CHECK (jsonb_typeof(policy)='object'),
            status VARCHAR(24) NOT NULL CHECK (status IN ('pending', 'partially_filled',
                'filled', 'cancelled', 'rejected')),
            terminal BOOLEAN NOT NULL,
            reason VARCHAR(100),
            created_at TIMESTAMPTZ NOT NULL,
            UNIQUE (portfolio_id, idempotency_key),
            FOREIGN KEY (recommendation_id, portfolio_id, strategy_version_id, snapshot_id)
                REFERENCES recommendation(id, portfolio_id, strategy_version_id, snapshot_id) ON
                    DELETE RESTRICT,
            CHECK (status NOT IN ('filled', 'cancelled', 'rejected') OR terminal),
            CHECK (status NOT IN ('cancelled', 'rejected') OR reason IS NOT NULL)
        );
        CREATE UNIQUE INDEX one_active_paper_batch ON paper_order_batch (portfolio_id) WHERE NOT
            terminal;
        CREATE TABLE paper_order (
            id UUID PRIMARY KEY,
            batch_id UUID NOT NULL REFERENCES paper_order_batch(id) ON DELETE RESTRICT,
            ordinal INTEGER NOT NULL CHECK (ordinal>=0),
            asset_id VARCHAR(160) NOT NULL CHECK (length(asset_id)>0),
            sector VARCHAR NOT NULL CHECK (length(sector)>0),
            side VARCHAR(4) NOT NULL CHECK (side IN ('BUY', 'SELL')),
            intent_key VARCHAR(256) NOT NULL CHECK (length(intent_key)>0),
            requested_quantity NUMERIC(30, 6) NOT NULL CHECK (requested_quantity>0 AND
                requested_quantity<1e24),
            filled_quantity NUMERIC(30, 6) NOT NULL CHECK (filled_quantity>=0 AND
                filled_quantity<1e24),
            pending_quantity NUMERIC(30, 6) NOT NULL CHECK (pending_quantity>=0 AND
                pending_quantity<1e24),
            closed_quantity NUMERIC(30, 6) NOT NULL CHECK (closed_quantity>=0 AND
                closed_quantity<1e24),
            status VARCHAR(24) NOT NULL CHECK (status IN ('pending', 'partially_filled',
                'filled', 'cancelled', 'rejected')),
            terminal BOOLEAN NOT NULL,
            reason VARCHAR(100),
            UNIQUE(batch_id, ordinal), UNIQUE(batch_id, intent_key),
            CHECK (requested_quantity=filled_quantity+pending_quantity+closed_quantity),
            CHECK (terminal=(pending_quantity=0)),
            CHECK (status!='filled' OR filled_quantity=requested_quantity),
            CHECK (status!='partially_filled' OR (filled_quantity>0 AND
                filled_quantity<requested_quantity)),
            CHECK (status NOT IN ('cancelled', 'rejected') OR (filled_quantity=0 AND terminal)),
            CHECK (status!='pending' OR (filled_quantity=0 AND NOT terminal))
        );
        CREATE TABLE paper_action_evidence (
            id UUID PRIMARY KEY,
            portfolio_id UUID NOT NULL REFERENCES paper_portfolio(id) ON DELETE RESTRICT,
            source_key VARCHAR(1024) NOT NULL,
            payload_sha256 VARCHAR(64) NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
            payload JSONB NOT NULL CHECK (jsonb_typeof(payload)='object'),
            recorded_at TIMESTAMPTZ NOT NULL,
            UNIQUE(portfolio_id, source_key, payload_sha256), UNIQUE(id, portfolio_id)
        );
        CREATE TABLE ledger_event (
            id UUID PRIMARY KEY,
            portfolio_id UUID NOT NULL REFERENCES paper_portfolio(id) ON DELETE RESTRICT,
            sequence BIGINT NOT NULL CHECK (sequence>0),
            portfolio_revision BIGINT NOT NULL CHECK (portfolio_revision>0),
            kind VARCHAR(40) NOT NULL CHECK (kind IN ('opening_funding', 'fill', 'order_closed',
                'split', 'dividend', 'entitlement', 'correction', 'strategy_binding',
                'batch_approval', 'batch_cancel')),
            event_key VARCHAR(256) NOT NULL CHECK (length(event_key)>0),
            payload_sha256 VARCHAR(64) NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
            recorded_at TIMESTAMPTZ NOT NULL,
            effective_at TIMESTAMPTZ NOT NULL,
            order_id UUID REFERENCES paper_order(id) ON DELETE RESTRICT,
            action_evidence_id UUID REFERENCES paper_action_evidence(id) ON DELETE RESTRICT,
            correction_target_id UUID REFERENCES ledger_event(id) ON DELETE RESTRICT,
            snapshot_id UUID REFERENCES dataset_snapshot(id) ON DELETE RESTRICT,
            strategy_version_id UUID NOT NULL REFERENCES strategy_version(id) ON DELETE RESTRICT,
            payload JSONB NOT NULL CHECK (
                jsonb_typeof(payload)='object'
                AND payload ?& ARRAY['before', 'after', 'command_sha256']
                AND jsonb_typeof(payload->'before')='object'
                AND jsonb_typeof(payload->'after')='object'
                AND (payload->'before') ?& ARRAY['cash_usd', 'positions', 'applied_actions',
                    'entitlements']
                AND (payload->'after') ?& ARRAY['cash_usd', 'positions', 'applied_actions',
                    'entitlements']
                AND jsonb_typeof(payload->'before'->'cash_usd')='string'
                AND jsonb_typeof(payload->'after'->'cash_usd')='string'
                AND jsonb_typeof(payload->'before'->'positions')='array'
                AND jsonb_typeof(payload->'after'->'positions')='array'
            ),
            UNIQUE(portfolio_id, sequence), UNIQUE(portfolio_id, event_key),
            UNIQUE(portfolio_id, portfolio_revision), UNIQUE(id, portfolio_id),
            FOREIGN KEY (correction_target_id, portfolio_id) REFERENCES ledger_event(id,
                portfolio_id) ON DELETE RESTRICT,
            FOREIGN KEY (action_evidence_id, portfolio_id) REFERENCES paper_action_evidence(id,
                portfolio_id) ON DELETE RESTRICT,
            CHECK ((kind IN ('fill', 'order_closed'))=(order_id IS NOT NULL)),
            CHECK ((kind='correction')=(correction_target_id IS NOT NULL))
        );
        ALTER TABLE paper_portfolio ADD CONSTRAINT fk_portfolio_opening FOREIGN KEY
            (opening_event_id)
            REFERENCES ledger_event(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;
        CREATE TABLE cash_ledger_entry (
            id UUID PRIMARY KEY,
            event_id UUID NOT NULL REFERENCES ledger_event(id) ON DELETE RESTRICT,
            purpose VARCHAR(40) NOT NULL,
            delta_usd NUMERIC(24, 2) NOT NULL CHECK (abs(delta_usd)<1e22),
            UNIQUE(event_id, purpose)
        );
        CREATE TABLE position_event (
            id UUID PRIMARY KEY,
            event_id UUID NOT NULL REFERENCES ledger_event(id) ON DELETE RESTRICT,
            asset_id VARCHAR(160) NOT NULL CHECK (length(asset_id)>0),
            sector VARCHAR NOT NULL CHECK (length(sector)>0),
            quantity_delta NUMERIC(30, 6) NOT NULL CHECK (abs(quantity_delta)<1e24),
            basis_delta_usd NUMERIC(24, 2) NOT NULL CHECK (abs(basis_delta_usd)<1e22),
            UNIQUE(event_id, asset_id)
        );
        CREATE TABLE paper_position (
            portfolio_id UUID NOT NULL REFERENCES paper_portfolio(id) ON DELETE RESTRICT,
            asset_id VARCHAR(160) NOT NULL CHECK (length(asset_id)>0),
            sector VARCHAR NOT NULL CHECK (length(sector)>0),
            quantity NUMERIC(30, 6) NOT NULL CHECK (quantity>=0 AND quantity<1e24),
            total_basis_usd NUMERIC(24, 2) NOT NULL CHECK (total_basis_usd>=0 AND
                total_basis_usd<1e22),
            last_sequence BIGINT NOT NULL CHECK (last_sequence>0),
            PRIMARY KEY(portfolio_id, asset_id),
            CHECK (quantity!=0 OR total_basis_usd=0),
            FOREIGN KEY (portfolio_id, last_sequence) REFERENCES ledger_event(portfolio_id,
                sequence) ON DELETE RESTRICT
        );
        CREATE TABLE paper_fill (
            id UUID PRIMARY KEY,
            order_id UUID NOT NULL REFERENCES paper_order(id) ON DELETE RESTRICT,
            event_id UUID NOT NULL UNIQUE REFERENCES ledger_event(id) ON DELETE RESTRICT,
            fill_event_key VARCHAR(256) NOT NULL,
            execution_session DATE NOT NULL,
            raw_price NUMERIC NOT NULL CHECK (raw_price>0 AND raw_price<'Infinity'::numeric),
            executed_price NUMERIC NOT NULL CHECK (executed_price>0 AND
                executed_price<'Infinity'::numeric),
            quantity NUMERIC(30, 6) NOT NULL CHECK (quantity>0 AND quantity<1e24),
            gross_usd NUMERIC(24, 2) NOT NULL CHECK (gross_usd>=0 AND gross_usd<1e22),
            fee_usd NUMERIC(24, 2) NOT NULL CHECK (fee_usd>=0 AND fee_usd<1e22),
            slippage_usd NUMERIC(24, 2) NOT NULL CHECK (slippage_usd>=0 AND slippage_usd<1e22),
            cash_delta_usd NUMERIC(24, 2) NOT NULL CHECK (abs(cash_delta_usd)<1e22),
            removed_basis_usd NUMERIC(24, 2) NOT NULL CHECK (removed_basis_usd>=0 AND
                removed_basis_usd<1e22),
            realized_pnl_usd NUMERIC(24, 2) NOT NULL CHECK (abs(realized_pnl_usd)<1e22),
            posted_at TIMESTAMPTZ NOT NULL,
            UNIQUE(order_id, fill_event_key)
        );
        CREATE INDEX ledger_history ON ledger_event(portfolio_id, sequence);
        CREATE INDEX paper_orders_by_batch ON paper_order(batch_id, ordinal);

        CREATE FUNCTION reject_paper_evidence_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Posted paper evidence is immutable'; END $$;
        CREATE TRIGGER immutable_ledger_event BEFORE UPDATE OR DELETE ON ledger_event
            FOR EACH ROW EXECUTE FUNCTION reject_paper_evidence_mutation();
        CREATE TRIGGER immutable_cash_entry BEFORE UPDATE OR DELETE ON cash_ledger_entry
            FOR EACH ROW EXECUTE FUNCTION reject_paper_evidence_mutation();
        CREATE TRIGGER immutable_position_event BEFORE UPDATE OR DELETE ON position_event
            FOR EACH ROW EXECUTE FUNCTION reject_paper_evidence_mutation();
        CREATE TRIGGER immutable_paper_fill BEFORE UPDATE OR DELETE ON paper_fill
            FOR EACH ROW EXECUTE FUNCTION reject_paper_evidence_mutation();
        CREATE TRIGGER immutable_action_evidence BEFORE UPDATE OR DELETE ON paper_action_evidence
            FOR EACH ROW EXECUTE FUNCTION reject_paper_evidence_mutation();

        CREATE FUNCTION protect_paper_intent() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE allowed TEXT[];
        BEGIN
            IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Referenced paper intent is retained'; END IF;
            IF TG_TABLE_NAME='recommendation' THEN allowed:=ARRAY['disposition'];
            ELSIF TG_TABLE_NAME='paper_order_batch' THEN allowed:=ARRAY['status', 'terminal',
                'reason'];
            ELSIF TG_TABLE_NAME='paper_order' THEN
                allowed:=ARRAY['filled_quantity', 'pending_quantity', 'closed_quantity',
                    'status', 'terminal', 'reason'];
            ELSE
                allowed:=ARRAY['cash_usd', 'revision', 'last_sequence', 'status',
                    'reconciliation_failed', 'state_metadata'];
                IF NEW.strategy_version_id IS DISTINCT FROM OLD.strategy_version_id THEN
                    IF EXISTS(SELECT 1 FROM paper_order_batch WHERE portfolio_id=OLD.id AND NOT
                        terminal)
                       OR NOT EXISTS(SELECT 1 FROM ledger_event WHERE portfolio_id=OLD.id
                          AND sequence=NEW.last_sequence AND kind='strategy_binding'
                          AND portfolio_revision=NEW.revision
                          AND payload->'command'->>'new_strategy_version_id'
                              =NEW.strategy_version_id::text)
                    THEN RAISE EXCEPTION 'Binding change requires explicit unreserved event';
                        END IF;
                    allowed:=array_append(allowed, 'strategy_version_id');
                END IF;
            END IF;
            IF (to_jsonb(OLD)-allowed) IS DISTINCT FROM (to_jsonb(NEW)-allowed)
            THEN RAISE EXCEPTION 'Authorized paper intent is immutable'; END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER immutable_portfolio_opening BEFORE UPDATE OR DELETE ON paper_portfolio
            FOR EACH ROW EXECUTE FUNCTION protect_paper_intent();
        CREATE TRIGGER immutable_recommendation_content BEFORE UPDATE OR DELETE ON recommendation
            FOR EACH ROW EXECUTE FUNCTION protect_paper_intent();
        CREATE TRIGGER immutable_batch_intent BEFORE UPDATE OR DELETE ON paper_order_batch
            FOR EACH ROW EXECUTE FUNCTION protect_paper_intent();
        CREATE TRIGGER immutable_order_intent BEFORE UPDATE OR DELETE ON paper_order
            FOR EACH ROW EXECUTE FUNCTION protect_paper_intent();

        CREATE FUNCTION validate_paper_event(event ledger_event) RETURNS void LANGUAGE plpgsql AS $$
        DECLARE c INTEGER; p INTEGER; f INTEGER; account paper_portfolio%ROWTYPE;
            asset TEXT; before_qty NUMERIC; after_qty NUMERIC; before_basis NUMERIC; after_basis
                NUMERIC;
            prior JSONB;
        BEGIN
            SELECT count(*) INTO c FROM cash_ledger_entry WHERE event_id=event.id;
            SELECT count(*) INTO p FROM position_event WHERE event_id=event.id;
            SELECT count(*) INTO f FROM paper_fill WHERE event_id=event.id;
            IF event.kind='fill' AND (c!=1 OR p!=1 OR f!=1) THEN
                RAISE EXCEPTION 'Fill requires one complete immutable accounting tuple';
            ELSIF event.kind IN ('opening_funding', 'dividend', 'correction') AND (c!=1 OR p!=0 OR
                f!=0) THEN
                RAISE EXCEPTION 'Cash event requires one cash entry';
            ELSIF event.kind='split' AND (c!=0 OR p>1 OR f!=0) THEN
                RAISE EXCEPTION 'Split must preserve cash and affect at most one position';
            ELSIF event.kind IN ('entitlement', 'order_closed', 'strategy_binding',
                'batch_approval', 'batch_cancel') AND (c!=0 OR
                p!=0 OR f!=0) THEN
                RAISE EXCEPTION 'Metadata event cannot invent economic effects';
            END IF;
            IF event.kind IN ('split', 'dividend', 'entitlement') AND event.action_evidence_id IS
                NULL THEN
                RAISE EXCEPTION 'Corporate action requires stable source evidence';
            END IF;
            IF EXISTS(SELECT 1 FROM paper_fill WHERE event_id=event.id AND order_id!=event.order_id)
                THEN
                RAISE EXCEPTION 'Fill/order lineage differs';
            END IF;
            IF event.kind='fill' AND EXISTS (
                SELECT 1 FROM paper_fill f
                JOIN paper_order o ON o.id=f.order_id
                JOIN position_event p ON p.event_id=event.id
                JOIN cash_ledger_entry c ON c.event_id=event.id
                WHERE f.event_id=event.id AND (
                    f.fill_event_key!=event.event_key OR p.asset_id!=o.asset_id
                    OR c.delta_usd!=f.cash_delta_usd OR NOT o.terminal
                    OR o.filled_quantity!=f.quantity OR o.pending_quantity!=0
                    OR p.quantity_delta!=CASE WHEN o.side='BUY' THEN f.quantity
                        ELSE -f.quantity END
                    OR p.basis_delta_usd!=CASE WHEN o.side='BUY' THEN -f.cash_delta_usd
                        ELSE -f.removed_basis_usd END
                    OR f.cash_delta_usd!=CASE WHEN o.side='BUY' THEN -(f.gross_usd+f.fee_usd)
                        ELSE f.gross_usd-f.fee_usd END
                    OR f.realized_pnl_usd!=CASE WHEN o.side='BUY' THEN 0
                        ELSE f.cash_delta_usd-f.removed_basis_usd END
                )
            ) THEN RAISE EXCEPTION 'Fill quantities, cash, basis or lifecycle disagree'; END IF;
            IF COALESCE((SELECT sum(delta_usd) FROM cash_ledger_entry WHERE event_id=event.id), 0)
                 != (event.payload->'after'->>'cash_usd')::numeric
                    - (event.payload->'before'->>'cash_usd')::numeric THEN
                RAISE EXCEPTION 'Cash effects differ from immutable transition';
            END IF;
            FOR asset IN
                SELECT value->>'asset_id' FROM
                    jsonb_array_elements(event.payload->'before'->'positions')
                UNION SELECT value->>'asset_id' FROM
                    jsonb_array_elements(event.payload->'after'->'positions')
                UNION SELECT asset_id FROM position_event WHERE event_id=event.id
            LOOP
                SELECT COALESCE((value->>'quantity')::numeric, 0),
                    COALESCE((value->>'total_basis_usd')::numeric, 0)
                    INTO before_qty, before_basis FROM
                        jsonb_array_elements(event.payload->'before'->'positions')
                    WHERE value->>'asset_id'=asset;
                SELECT COALESCE((value->>'quantity')::numeric, 0),
                    COALESCE((value->>'total_basis_usd')::numeric, 0)
                    INTO after_qty, after_basis FROM
                        jsonb_array_elements(event.payload->'after'->'positions')
                    WHERE value->>'asset_id'=asset;
                IF COALESCE((SELECT sum(quantity_delta) FROM position_event WHERE
                    event_id=event.id AND asset_id=asset), 0)
                       != COALESCE(after_qty, 0)-COALESCE(before_qty, 0)
                   OR COALESCE((SELECT sum(basis_delta_usd) FROM position_event WHERE
                       event_id=event.id AND asset_id=asset), 0)
                       != COALESCE(after_basis, 0)-COALESCE(before_basis, 0)
                THEN RAISE EXCEPTION 'Position effects differ from immutable transition'; END IF;
            END LOOP;
            IF event.sequence=1 THEN
                IF event.kind!='opening_funding'
                   OR (event.payload->'before'->>'cash_usd')::numeric!=0
                   OR jsonb_array_length(event.payload->'before'->'positions')!=0
                THEN RAISE EXCEPTION 'Ledger starts from zero with opening funding'; END IF;
            ELSE
                SELECT payload->'after' INTO prior FROM ledger_event
                    WHERE portfolio_id=event.portfolio_id AND sequence=event.sequence-1;
                IF prior IS NULL OR prior IS DISTINCT FROM event.payload->'before'
                THEN RAISE EXCEPTION 'Ledger transition chain is incomplete'; END IF;
            END IF;
            SELECT * INTO account FROM paper_portfolio WHERE id=event.portfolio_id;
            IF account.last_sequence<event.sequence OR
                account.revision<event.portfolio_revision THEN
                RAISE EXCEPTION 'Projection did not advance with its event';
            END IF;
            IF account.last_sequence=event.sequence AND
                account.cash_usd!=(event.payload->'after'->>'cash_usd')::numeric THEN
                RAISE EXCEPTION 'Latest cash projection differs from event';
            END IF;
            IF event.kind='opening_funding' AND (event.sequence!=1 OR
                account.opening_event_id!=event.id
                OR account.opening_cash_usd!=(event.payload->'after'->>'cash_usd')::numeric) THEN
                RAISE EXCEPTION 'Opening funding must be the account root';
            END IF;
            RETURN;
        END $$;
        CREATE FUNCTION complete_paper_event() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN PERFORM validate_paper_event(NEW); RETURN NEW; END $$;
        CREATE FUNCTION complete_paper_child() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE parent ledger_event%ROWTYPE;
        BEGIN
            SELECT * INTO STRICT parent FROM ledger_event WHERE id=NEW.event_id;
            PERFORM validate_paper_event(parent);
            RETURN NEW;
        END $$;
        CREATE CONSTRAINT TRIGGER complete_cash_tuple AFTER INSERT ON cash_ledger_entry
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION complete_paper_child();
        CREATE CONSTRAINT TRIGGER complete_position_tuple AFTER INSERT ON position_event
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION complete_paper_child();
        CREATE CONSTRAINT TRIGGER complete_fill_tuple AFTER INSERT ON paper_fill
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION complete_paper_child();
        CREATE CONSTRAINT TRIGGER complete_paper_event AFTER INSERT ON ledger_event
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION complete_paper_event();
    """)


def downgrade() -> None:
    raise RuntimeError("Paper ledger evidence is retained; restore a verified backup to downgrade")
