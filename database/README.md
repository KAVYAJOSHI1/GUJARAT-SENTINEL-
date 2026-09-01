# SENTINEL Database Schemas & Migrations

Owner: **Vanshal**
Branch: `feature/vanshal-backend`

## Database Schema Tables
1. `cameras`: Camera catalogue, location (PostGIS POINT), RTSP stream URI, health status
2. `vehicle_events`: Detected vehicle events, ANPR plate number, confidence, timestamp, evidence URI
3. `watchlist`: Target vehicle registration numbers, threat category, priority level
4. `alerts`: Triggered alert records, matched watchlist entry, operator acknowledgment status
5. `users`: User authentication, roles, department assignment
6. `audit_logs`: Operational activity logs
