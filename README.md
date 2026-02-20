# 🧠🚀 STUDILO Backend
### *From Aerospace Engineering frustration to a high-performance AI Tutor.*

---

## 📖 The "Why"
**STUDILO** was born from a very real, very frustrating necessity. While studying for critical exams in **Aerospace Mechanics**, the creator found that theoretical knowledge wasn't enough to pass without active practice. 

This isn't just another chatbot; it is a backend engine designed to **actively challenge** students. It generates dynamic study plans and progressive exams based strictly on user-provided notes, eliminating AI "hallucinations" through rigorous **Retrieval-Augmented Generation (RAG)**.

---

## 🏗️ System Design & Architecture
Built with enterprise-grade scalability and reliability based on the **Alex Xu Framework**.

### 1. Scalability & State
* **Stateless Architecture**: The API layer holds no state; sessions are managed via **JWT** and external **Redis** clusters to allow for infinite horizontal scaling.
* **Horizontal Scaling**: Designed to handle increased load by adding more instances rather than just bigger hardware.
* **Load Balancing**: Implements distribution algorithms like **Round Robin** or **Least Connections** to handle traffic efficiently across instances.

### 2. Reliability & Decoupling
* **Async Processing**: Heavy tasks (OCR, PDF Chunking) are decoupled from the main gateway using **Message Queues (RabbitMQ)** to prevent bottlenecks during peak traffic.
* **No SPOF (Single Point of Failure)**: Every component is redundant. We use **PostgreSQL** with read replicas and automated failover to ensure the system never stays down.
* **Fault Tolerance**: Implements patterns like **Retry with Backoff** and **Circuit Breakers** to handle service failures gracefully.

### 3. Technical Rigor & Performance
* **Vector Precision**: Uses **Qdrant** for semantic search, ensuring the AI only answers based on the context of your uploaded files.
* **Multi-level Caching**: Utilizes a tiered strategy—from Browser to Database cache—to ensure sub-second response times.
* **Observability**: Built-in monitoring of "Golden Signals" (Latency, Traffic, Errors, Saturation) to ensure system health.

---

## 💻 Tech Stack
| Component | Technology |
| :--- | :--- |
| **Orchestration & API** | FastAPI (Python) |
| **Relational Database** | PostgreSQL (High Availability) |
| **Cache & Sessions** | Redis Cluster (via Sentinel) |
| **Message Broker** | RabbitMQ |
| **Vector Engine** | Qdrant |
| **Object Storage** | MinIO (S3-Compatible) |
| **Observability** | Prometheus, Grafana, & ELK Stack |

---
*This project is a practical implementation of the principles found in Alex Xu's "System Design Interview".*
