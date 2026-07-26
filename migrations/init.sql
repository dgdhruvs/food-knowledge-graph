-- Initial PostgreSQL schema setup for Food Knowledge Graph
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================================
-- ENUM TYPES (Idempotent creation)
-- ============================================================
DO $$ BEGIN
    CREATE TYPE review_status AS ENUM ('pending', 'auto_approved', 'human_approved', 'rejected', 'flagged');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE source_type AS ENUM ('government', 'wikipedia', 'encyclopedia', 'academic', 'recipe_site', 'community', 'open_dataset', 'archive');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE meal_type AS ENUM ('breakfast', 'lunch', 'dinner', 'snack', 'dessert', 'beverage', 'street_food', 'festival', 'brunch');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE crawl_status AS ENUM ('queued', 'fetching', 'fetched', 'parsed', 'failed', 'dead', 'skipped');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE agent_type AS ENUM ('country', 'cuisine', 'dish_discovery', 'dish_information');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE rule_severity AS ENUM ('error', 'warning', 'info');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE conflict_resolution AS ENUM ('source_priority', 'human_review', 'majority_vote', 'most_recent');
EXCEPTION WHEN duplicate_object THEN null; END $$;

-- ============================================================
-- SOURCES
-- ============================================================
CREATE TABLE IF NOT EXISTS sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url TEXT NOT NULL UNIQUE,
    domain TEXT NOT NULL,
    source_type source_type NOT NULL,
    trust_score FLOAT NOT NULL CHECK (trust_score BETWEEN 0 AND 1),
    language VARCHAR(10),
    country_iso VARCHAR(3),
    crawl_priority INT DEFAULT 5 CHECK (crawl_priority BETWEEN 1 AND 10),
    refresh_interval_hours INT DEFAULT 168,
    last_crawled_at TIMESTAMPTZ,
    next_crawl_at TIMESTAMPTZ,
    robots_txt_url TEXT,
    robots_cached_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- CRAWL JOBS
-- ============================================================
CREATE TABLE IF NOT EXISTS crawl_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID REFERENCES sources(id),
    url TEXT NOT NULL,
    status crawl_status NOT NULL DEFAULT 'queued',
    attempt_count INT DEFAULT 0,
    http_status INT,
    etag TEXT,
    last_modified TIMESTAMPTZ,
    content_hash CHAR(64),
    s3_raw_key TEXT,
    s3_screenshot_key TEXT,
    crawl_duration_ms INT,
    error_message TEXT,
    queued_at TIMESTAMPTZ DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    worker_id TEXT,
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_crawl_jobs_status ON crawl_jobs(status);
CREATE INDEX IF NOT EXISTS idx_crawl_jobs_source_id ON crawl_jobs(source_id);
CREATE INDEX IF NOT EXISTS idx_crawl_jobs_queued_at ON crawl_jobs(queued_at);

-- ============================================================
-- PARSED PAGES
-- ============================================================
CREATE TABLE IF NOT EXISTS parsed_pages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crawl_job_id UUID REFERENCES crawl_jobs(id),
    url TEXT NOT NULL,
    canonical_url TEXT,
    language VARCHAR(10),
    title TEXT,
    main_text TEXT,
    structured_data JSONB,
    tables JSONB,
    lists JSONB,
    metadata JSONB,
    parse_version VARCHAR(20),
    parsed_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- NORMALIZED CANDIDATES
-- ============================================================
CREATE TABLE IF NOT EXISTS normalized_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parsed_page_id UUID REFERENCES parsed_pages(id),
    normalized_json JSONB NOT NULL,
    normalization_version VARCHAR(20),
    language_original VARCHAR(10),
    language_detected VARCHAR(10),
    normalization_log JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- COUNTRIES
-- ============================================================
CREATE TABLE IF NOT EXISTS countries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    native_name TEXT,
    iso_alpha2 CHAR(2) UNIQUE,
    iso_alpha3 CHAR(3) UNIQUE,
    iso_numeric VARCHAR(5),
    region TEXT,
    sub_region TEXT,
    intermediate_region TEXT,
    languages TEXT[],
    aliases TEXT[],
    review_status review_status DEFAULT 'auto_approved',
    confidence FLOAT DEFAULT 1.0,
    source_ids UUID[],
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- TERRITORIES & STATES
-- ============================================================
CREATE TABLE IF NOT EXISTS territories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    sovereign_country_id UUID REFERENCES countries(id),
    type TEXT,
    aliases TEXT[],
    confidence FLOAT DEFAULT 1.0
);

CREATE TABLE IF NOT EXISTS states (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    country_id UUID NOT NULL REFERENCES countries(id),
    aliases TEXT[],
    confidence FLOAT DEFAULT 1.0,
    UNIQUE(name, country_id)
);

CREATE TABLE IF NOT EXISTS cultural_regions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    country_ids UUID[]
);

-- ============================================================
-- CUISINES
-- ============================================================
CREATE TABLE IF NOT EXISTS cuisines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    native_name TEXT,
    description TEXT,
    parent_cuisine_id UUID REFERENCES cuisines(id),
    country_id UUID REFERENCES countries(id),
    cultural_region_id UUID REFERENCES cultural_regions(id),
    cuisine_type TEXT,
    aliases TEXT[],
    review_status review_status DEFAULT 'auto_approved',
    confidence FLOAT,
    source_ids UUID[],
    version INT DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- INGREDIENTS
-- ============================================================
CREATE TABLE IF NOT EXISTS ingredients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    aliases TEXT[],
    category TEXT,
    is_vegan BOOLEAN,
    is_allergen BOOLEAN DEFAULT FALSE,
    allergen_types TEXT[],
    nutritional_profile JSONB,
    review_status review_status DEFAULT 'auto_approved',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- COOKING METHODS & EQUIPMENT
-- ============================================================
CREATE TABLE IF NOT EXISTS cooking_methods (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    heat_required BOOLEAN DEFAULT TRUE,
    aliases TEXT[]
);

CREATE TABLE IF NOT EXISTS cooking_equipment (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    aliases TEXT[]
);

-- ============================================================
-- DISHES (Core table)
-- ============================================================
CREATE TABLE IF NOT EXISTS dishes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    native_name TEXT,
    english_name TEXT,
    aliases TEXT[],
    description TEXT,
    cuisine_id UUID REFERENCES cuisines(id),
    country_id UUID REFERENCES countries(id),
    state_id UUID REFERENCES states(id),
    cultural_region_id UUID REFERENCES cultural_regions(id),
    category TEXT,
    meal_types meal_type[],
    taste_profile TEXT[],
    texture TEXT,
    aroma TEXT,
    color TEXT,
    prep_time_min INT,
    cook_time_min INT,
    serving_size_g FLOAT,

    is_vegetarian BOOLEAN,
    is_vegan BOOLEAN,
    is_gluten_free BOOLEAN,
    contains_dairy BOOLEAN,
    contains_egg BOOLEAN,
    contains_meat BOOLEAN,
    contains_seafood BOOLEAN,
    allergens TEXT[],
    diet_types TEXT[],

    history TEXT,
    origin_description TEXT,
    interesting_facts TEXT[],
    festival_id UUID,
    seasonality TEXT[],

    review_status review_status DEFAULT 'pending',
    confidence FLOAT,
    source_ids UUID[],
    canonical_dish_id UUID,
    version INT DEFAULT 1,

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),

    CONSTRAINT dishes_name_cuisine_unique UNIQUE (name, cuisine_id)
);

CREATE INDEX IF NOT EXISTS idx_dishes_cuisine_id ON dishes(cuisine_id);
CREATE INDEX IF NOT EXISTS idx_dishes_country_id ON dishes(country_id);
CREATE INDEX IF NOT EXISTS idx_dishes_review_status ON dishes(review_status);
CREATE INDEX IF NOT EXISTS idx_dishes_name_trgm ON dishes USING gin(name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_dishes_aliases ON dishes USING gin(aliases);

-- ============================================================
-- DISH INGREDIENTS (Junction)
-- ============================================================
CREATE TABLE IF NOT EXISTS dish_ingredients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dish_id UUID NOT NULL REFERENCES dishes(id) ON DELETE CASCADE,
    ingredient_id UUID NOT NULL REFERENCES ingredients(id),
    is_optional BOOLEAN DEFAULT FALSE,
    amount TEXT,
    unit TEXT,
    preparation_note TEXT,
    UNIQUE(dish_id, ingredient_id)
);

-- ============================================================
-- DISH RELATIONSHIPS
-- ============================================================
CREATE TABLE IF NOT EXISTS dish_similarities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dish_id_a UUID NOT NULL REFERENCES dishes(id),
    dish_id_b UUID NOT NULL REFERENCES dishes(id),
    similarity_score FLOAT NOT NULL,
    similarity_type TEXT,
    CHECK (dish_id_a < dish_id_b)
);

CREATE TABLE IF NOT EXISTS dish_variants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_dish_id UUID NOT NULL REFERENCES dishes(id),
    variant_dish_id UUID NOT NULL REFERENCES dishes(id),
    variant_type TEXT,
    description TEXT
);

-- ============================================================
-- NUTRITION
-- ============================================================
CREATE TABLE IF NOT EXISTS nutrition_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dish_id UUID NOT NULL REFERENCES dishes(id),
    calories_kcal FLOAT,
    protein_g FLOAT,
    carbohydrates_g FLOAT,
    fat_g FLOAT,
    saturated_fat_g FLOAT,
    fiber_g FLOAT,
    sugar_g FLOAT,
    sodium_mg FLOAT,
    per_serving_g FLOAT,
    source TEXT,
    confidence FLOAT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- FESTIVALS & SEASONS
-- ============================================================
CREATE TABLE IF NOT EXISTS festivals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    country_ids UUID[],
    month_start INT,
    month_end INT,
    is_religious BOOLEAN DEFAULT FALSE,
    religion TEXT,
    description TEXT
);

CREATE TABLE IF NOT EXISTS dish_festivals (
    dish_id UUID REFERENCES dishes(id),
    festival_id UUID REFERENCES festivals(id),
    PRIMARY KEY (dish_id, festival_id)
);

CREATE TABLE IF NOT EXISTS dish_seasons (
    dish_id UUID REFERENCES dishes(id),
    season TEXT,
    country_id UUID REFERENCES countries(id),
    PRIMARY KEY (dish_id, season, country_id)
);

-- ============================================================
-- AI AGENT RUNS
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    normalized_candidate_id UUID REFERENCES normalized_candidates(id),
    agent_type agent_type NOT NULL,
    model_name TEXT,
    model_version TEXT,
    input_tokens INT,
    output_tokens INT,
    latency_ms INT,
    raw_output JSONB,
    parsed_output JSONB,
    confidence FLOAT,
    validation_passed BOOLEAN,
    validation_errors JSONB,
    retry_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- RULE VIOLATIONS
-- ============================================================
CREATE TABLE IF NOT EXISTS rule_violations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_run_id UUID REFERENCES agent_runs(id),
    rule_id TEXT NOT NULL,
    rule_name TEXT,
    severity rule_severity NOT NULL,
    message TEXT,
    field TEXT,
    value TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- HUMAN REVIEW QUEUE
-- ============================================================
CREATE TABLE IF NOT EXISTS review_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT NOT NULL,
    entity_id UUID,
    agent_run_id UUID REFERENCES agent_runs(id),
    reason TEXT NOT NULL,
    reason_codes TEXT[],
    priority INT DEFAULT 5,
    confidence FLOAT,
    assigned_to TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT now(),
    claimed_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ
);

-- ============================================================
-- AUDIT LOG
-- ============================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_type TEXT NOT NULL,
    actor_id TEXT,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id UUID,
    before_state JSONB,
    after_state JSONB,
    reason TEXT,
    ip_address INET,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor ON audit_log(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at);

-- ============================================================
-- PROVENANCE / DATA LINEAGE
-- ============================================================
CREATE TABLE IF NOT EXISTS provenance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT NOT NULL,
    entity_id UUID NOT NULL,
    source_id UUID REFERENCES sources(id),
    crawl_job_id UUID REFERENCES crawl_jobs(id),
    parsed_page_id UUID REFERENCES parsed_pages(id),
    agent_run_id UUID REFERENCES agent_runs(id),
    field_name TEXT,
    field_value TEXT,
    confidence FLOAT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- ALIASES (Global alias resolution table)
-- ============================================================
CREATE TABLE IF NOT EXISTS entity_aliases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT NOT NULL,
    entity_id UUID NOT NULL,
    alias TEXT NOT NULL,
    language VARCHAR(10),
    region TEXT,
    is_canonical BOOLEAN DEFAULT FALSE,
    UNIQUE(entity_type, alias, language)
);

CREATE INDEX IF NOT EXISTS idx_entity_aliases_alias ON entity_aliases USING gin(to_tsvector('simple', alias));
