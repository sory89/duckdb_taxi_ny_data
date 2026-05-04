-- 03. Fare per mile by borough

SELECT
    z.Borough,
    round(sum(fare_amount) / sum(trip_distance), 2) AS fare_per_mile_usd,
    count(*) AS trips
FROM trips t
JOIN zones z ON t.PULocationID = z.LocationID
WHERE trip_distance > 0.1
  AND fare_amount > 0
  AND z.Borough <> 'Unknown'
GROUP BY z.Borough
ORDER BY fare_per_mile_usd DESC;


-- 04. Multi-file glob + predicate pushdown
-- Read three months in one query. DuckDB uses the parquet row-group
-- statistics to skip ranges that can't match the date filter, and
-- fetches only the byte ranges over HTTPS. Watch the timer.

SELECT
    date_trunc('month', tpep_pickup_datetime) AS month,
    count(*) AS trips,
    round(avg(tip_amount), 2) AS avg_tip_usd,
    round(avg(trip_distance), 2) AS avg_miles
FROM read_parquet([
    'https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2024-01.parquet',
    'https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2024-02.parquet',
    'https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2024-03.parquet'
])
WHERE tpep_pickup_datetime >= TIMESTAMP '2024-01-15'
  AND tpep_pickup_datetime < TIMESTAMP '2024-02-15'
GROUP BY month
ORDER BY month;

-- Pretty output for the camera
.mode duckbox
.timer on

-- 1. Turn on the https extension.
-- This is what lets DuckDB read parquet straight off the web —
-- no download, no staging, no S3 client.

INSTALL https;
LOAD https;

-- 2. Point a view at the public NYC TLC parquet file.
-- The TLC publishes one parquet per month at a stable CloudFront URL.
-- Nothing is fetched yet — DuckDB just reads the footer to learn the schema.

CREATE OR REPLACE VIEW trips AS
SELECT *
FROM read_parquet(
  'https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2024-01.parquet'
);

-- Take a peek at the schema (no rows fetched).
DESCRIBE trips;

-- And the row count for one month of yellow-cab trips.
SELECT count(*) AS total_trips FROM trips;

-- 3. Pull in the zone lookup so we can talk in human terms
-- (LocationID -> Borough, Zone).

CREATE OR REPLACE VIEW zones AS
SELECT *
FROM read_csv(
  'https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv'
);

-- 04. Multi-file glob + predicate pushdown
-- Read three months in one query. DuckDB uses the parquet row-group
-- statistics to skip ranges that can't match the date filter, and
-- fetches only those byte ranges over HTTPS. Watch the timer.

SELECT
    date_trunc('month', tpep_pickup_datetime) AS month,
    count(*) AS trips,
    round(avg(tip_amount), 2) AS avg_tip_usd,
    round(avg(trip_distance), 2) AS avg_miles
FROM read_parquet([
    'https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2024-01.parquet',
    'https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2024-02.parquet',
    'https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2024-03.parquet'
])
WHERE tpep_pickup_datetime >= TIMESTAMP '2024-01-15'
  AND tpep_pickup_datetime < TIMESTAMP '2024-02-15'
GROUP BY month
ORDER BY month;