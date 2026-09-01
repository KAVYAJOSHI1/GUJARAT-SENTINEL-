# SENTINEL — Cybersecurity, RBAC & Audit Compliance

---

## 1. Security Architecture Matrix

1. **Authentication**: OAuth2 with JWT bearer tokens (RS256 signature verification, 8-hour session expiry).
2. **Role-Based Access Control (RBAC)**:
   - `ADMIN`: Full system configuration, user creation, camera ingestion management.
   - `OFFICER`: Vehicle search, investigation console, PDF evidence export, alert acknowledgment.
   - `OPERATOR`: Real-time dashboard view & alert monitoring.
3. **Data Encryption**:
   - In-Transit: TLS 1.3 encryption across HTTP APIs, WebSockets, and database connections.
   - At-Rest: AES-256 server-side encryption for evidence snapshot files stored in MinIO.
4. **Audit Logging**: Immutable system audit trail (`audit_logs` table) recording user login, search query, evidence export, and alert acknowledgment events.
