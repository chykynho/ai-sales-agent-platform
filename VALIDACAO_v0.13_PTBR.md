# Validação v0.13 — Resiliência/Performance

Critérios de aceite:

1. API v0.13 pronta com PostgreSQL e Redis;
2. regressão completa sem falhas;
3. endpoint autenticado `/api/v1/resilience/config` disponível;
4. headers `X-RateLimit-*` presentes em endpoint protegido;
5. rate limiter real em Redis: 3 aceitas + 1 rejeitada em namespace de smoke;
6. circuit breaker real em Redis: open -> reject -> half-open -> closed;
7. bulkhead rejeita excesso de concorrência;
8. retry helper recupera falha transitória controlada;
9. métricas Prometheus de resiliência disponíveis;
10. carga segura com error rate <= 1% e p95 <= 750 ms no ambiente local de referência.

O smoke usa namespaces isolados e limpa as chaves Redis após a validação.
