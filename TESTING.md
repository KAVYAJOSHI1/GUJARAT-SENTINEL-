# SENTINEL — Master Testing & Verification Blueprint

---

## 1. Multi-Level Testing Suite

1. **Unit Testing**:
   - AI Plate Normalization Regex: Test dirty inputs (`GJ-01 AB 1234`, `G.J.01.AB.1234`).
   - Multi-Frame Consensus Voting: Verify majority vote calculation across noisy candidate strings.
   - Alert Cooldown Deduplication: Verify duplicate alert suppression within 300 seconds.
2. **Integration Testing**:
   - AI Payload Ingestion: Verify `POST /api/v1/events/ai-detection` writes to PostgreSQL and MinIO.
   - WebSocket Broadcast: Test alert push notification receipt on simulated client connections.
3. **Feed Failure Injection Suite**:
   - Stream Disconnect Test: Kill RTSP server feed and verify exponential backoff retry timestamps (`2s -> 4s -> 8s -> 16s -> 30s`).
