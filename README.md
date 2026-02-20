🧠🚀 STUDILO Backend
From Aerospace Engineering frustration to a high-performance AI Tutor.

📖 The "Why"
Born from the lack of practice tools for Aerospace Mechanics, STUDILO isn't just another chatbot. It is a backend engine designed to actively challenge students. It generates dynamic study plans and progressive exams based strictly on user-provided notes, eliminating AI hallucinations through rigorous RAG (Retrieval-Augmented Generation).
+3

🏗️ System Design & Architecture
Built with enterprise-grade scalability and reliability as the foundation.
+1

1. Scalability & State

Stateless Architecture: The API layer holds no state; sessions are managed via JWT and external Redis clusters to allow for infinite horizontal scaling.
+2


Load Balancing: Implements distribution algorithms (Round Robin/Least Connections) to handle traffic efficiently across instances.
+1

2. Reliability & Decoupling

Async Processing: Heavy tasks (OCR, PDF Chunking) are decoupled from the main gateway using RabbitMQ. This prevents bottlenecks during peak traffic.
+2

No SPOF: Every component is redundant. We use PostgreSQL with read replicas and automated failover to ensure the system never stays down.
+1

3. Technical Rigor (RAG)

Vector Precision: Uses Qdrant for semantic search, ensuring the AI only answers based on the context of your uploaded files.
+1


Performance: Multi-level caching (CDN, Application, Database) ensures sub-second response times.
+1

💻 Tech Stack

API: FastAPI (Python).

Storage: PostgreSQL (HA) + MinIO (S3-Compatible).

Cache & Queue: Redis Cluster + RabbitMQ.


Observability: Prometheus, Grafana, and ELK Stack.
+1

🚀 Quick Start
Clone: git clone https://github.com/MiquelBerenguer/STUDILO.git

Config: cp .env.example .env (Add your OpenAI/Google keys).

Deploy: docker-compose up -d