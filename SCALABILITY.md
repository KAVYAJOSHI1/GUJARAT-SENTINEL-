# SENTINEL — Statewide Scalability Roadmap (50 to 80,000 Cameras)

---

## 1. Multi-Tier Scaling Strategy

| Scale Tier | Camera Count | Ingestion Throughput | Primary Infrastructure Strategy |
| :--- | :--- | :--- | :--- |
| **PoC Phase** | ~50 Feeds | ~1,250 FPS Total | Single node Docker Compose stack |
| **Regional Node** | ~2,500 Feeds | ~62,500 FPS Total | Edge gateway clusters + Distributed Kafka |
| **Statewide Grid** | ~80,000 Feeds | ~2,000,000 FPS Total | Kubernetes (K8s) auto-scaling + MinIO distributed Object Storage |

---

## 2. Horizontal Ingestion & AI Worker Pools

To support 80,000 streams:
1. Stream ingestion workers decouple from AI inference using Kafka/RabbitMQ frame queues.
2. AI inference nodes auto-scale based on queue backlog metrics using NVIDIA Triton Inference Server.
3. PostgreSQL partition management separates historical logs from active hot queries.
