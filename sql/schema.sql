CREATE TABLE IF NOT EXISTS nasa_records (
    source_api TEXT NOT NULL,
    source_id TEXT NOT NULL,
    date DATE NOT NULL,
    title TEXT NOT NULL,
    media_type TEXT,
    image_url TEXT,
    page_url TEXT,
    asset_manifest_url TEXT,
    explanation TEXT,
    credit TEXT,
    alt_text TEXT,
    center TEXT,
    location TEXT,
    keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
    PRIMARY KEY (source_api, source_id)
);

CREATE TABLE IF NOT EXISTS nasa_search_matches (
    source_api TEXT NOT NULL,
    source_id TEXT NOT NULL,
    search_keyword TEXT NOT NULL,
    PRIMARY KEY (source_api, source_id, search_keyword),
    FOREIGN KEY (source_api, source_id)
        REFERENCES nasa_records (source_api, source_id)
);