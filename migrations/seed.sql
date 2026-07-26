-- Seed Base Reference Data: Countries, Cuisines, and Seed Sources

-- 1. Countries
INSERT INTO countries (id, name, iso_alpha2, iso_alpha3, region, sub_region) VALUES
  ('11111111-1111-1111-1111-111111111111', 'India', 'IN', 'IND', 'Asia', 'Southern Asia'),
  ('22222222-2222-2222-2222-222222222222', 'Italy', 'IT', 'ITA', 'Europe', 'Southern Europe'),
  ('33333333-3333-3333-3333-333333333333', 'Japan', 'JP', 'JPN', 'Asia', 'Eastern Asia'),
  ('44444444-4444-4444-4444-444444444444', 'Mexico', 'MX', 'MEX', 'Americas', 'Central America'),
  ('55555555-5555-5555-5555-555555555555', 'France', 'FR', 'FRA', 'Europe', 'Western Europe')
ON CONFLICT (name) DO NOTHING;

-- 2. Cuisines
INSERT INTO cuisines (id, name, country_id, cuisine_type, confidence) VALUES
  ('a1111111-1111-1111-1111-111111111111', 'Indian Cuisine', '11111111-1111-1111-1111-111111111111', 'national', 1.0),
  ('a2222222-2222-2222-2222-222222222222', 'Italian Cuisine', '22222222-2222-2222-2222-222222222222', 'national', 1.0),
  ('a3333333-3333-3333-3333-333333333333', 'Japanese Cuisine', '33333333-3333-3333-3333-333333333333', 'national', 1.0),
  ('a4444444-4444-4444-4444-444444444444', 'Mexican Cuisine', '44444444-4444-4444-4444-444444444444', 'national', 1.0)
ON CONFLICT (name) DO NOTHING;

-- 3. High-Quality Seed Sources
INSERT INTO sources (id, url, domain, source_type, trust_score, language, country_iso, crawl_priority) VALUES
  ('b1111111-1111-1111-1111-111111111111', 'https://en.wikipedia.org/wiki/List_of_Indian_dishes', 'en.wikipedia.org', 'wikipedia', 0.95, 'en', 'IND', 9),
  ('b2222222-2222-2222-2222-222222222222', 'https://en.wikipedia.org/wiki/List_of_Italian_dishes', 'en.wikipedia.org', 'wikipedia', 0.95, 'en', 'ITA', 9),
  ('b3333333-3333-3333-3333-333333333333', 'https://en.wikipedia.org/wiki/List_of_Japanese_dishes', 'en.wikipedia.org', 'wikipedia', 0.95, 'en', 'JPN', 9),
  ('b4444444-4444-4444-4444-444444444444', 'https://en.wikipedia.org/wiki/List_of_Mexican_dishes', 'en.wikipedia.org', 'wikipedia', 0.95, 'en', 'MEX', 9)
ON CONFLICT (url) DO NOTHING;

-- 4. Queue Crawl Jobs
INSERT INTO crawl_jobs (source_id, url, status)
SELECT id, url, 'queued'::crawl_status FROM sources
ON CONFLICT DO NOTHING;
