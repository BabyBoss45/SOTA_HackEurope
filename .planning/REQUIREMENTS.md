# Requirements: SOTA Hackathon Polish

**Defined:** 2026-03-14
**Core Value:** Весь user flow от описания задачи до оплаты работает без багов при live demo

## v1 Requirements

### Job Pipeline

- [ ] **JOB-01**: Джоб созданный через Butler чат появляется на маркетплейсе (Butler -> PostgreSQL -> Marketplace UI)
- [ ] **JOB-02**: Статусы джобов на маркетплейсе синхронизированы с реальными фазами (open -> selecting -> assigned -> completed)
- [ ] **JOB-03**: Убрать или чётко пометить захардкоженные демо-данные на маркетплейсе

### Bidding

- [x] **BID-01**: 15-секундный таймер биддинга не сбрасывается при новых сообщениях в чате (использовать useRef + absolute timestamp)

### Payment

- [ ] **PAY-01**: При оплате пользователь видит два равных варианта: Stripe (USD) и крипто-кошелёк (USDC)
- [ ] **PAY-02**: Убрать auto-connect кошелька при загрузке страницы -- подключение кошелька только при выборе крипто-оплаты

### UI Polish

- [ ] **UI-01**: Редизайн полей ввода на экране логина мобильного приложения -- аккуратные, mobile-friendly поля

## v2 Requirements

### Reliability

- **REL-01**: Webhook retry с exponential backoff для developer endpoints
- **REL-02**: Idempotency keys для Stripe и Solana транзакций

### Security

- **SEC-01**: Rate limiting на публичных endpoints
- **SEC-02**: CSRF protection на state-modifying API routes

## Out of Scope

| Feature | Reason |
|---------|--------|
| Тесты | Не до демо -- хакатон |
| Rate limiting | Не влияет на демо |
| Monitoring/observability | Нет времени |
| Mobile native app | Фокус на веб |
| Новые фичи | Только фиксы существующего |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| JOB-01 | Phase 1 | Pending |
| JOB-02 | Phase 3 | Pending |
| JOB-03 | Phase 1 | Pending |
| BID-01 | Phase 2 | Complete |
| PAY-01 | Phase 4 | Pending |
| PAY-02 | Phase 4 | Pending |
| UI-01 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 7 total
- Mapped to phases: 7
- Unmapped: 0

---
*Requirements defined: 2026-03-14*
*Last updated: 2026-03-14 after roadmap creation*
