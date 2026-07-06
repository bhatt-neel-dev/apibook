-- Add payload columns for request/response monitoring
-- Migration: 003_request_response_payloads

ALTER TABLE api_requests ADD COLUMN IF NOT EXISTS request_payload String CODEC(ZSTD(3));
ALTER TABLE api_requests ADD COLUMN IF NOT EXISTS response_payload String CODEC(ZSTD(3));
