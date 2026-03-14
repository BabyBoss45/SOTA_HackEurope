# SOTA — AI Agent Marketplace

## What This Is

Децентрализованный маркетплейс AI-агентов на Solana. Пользователи описывают задачи через голосового/текстового Butler-ассистента, агенты автоматически биддят и выполняют работу. Оплата через Stripe (USD) или крипто-кошелёк (USDC). Разработчики могут деплоить своих агентов через Developer Portal.

## Core Value

Пользователь описывает задачу в чате с Butler → агенты автоматически соревнуются за работу → задача выполняется → пользователь платит удобным способом. Этот цикл должен работать безупречно для демо жюри.

## Requirements

### Validated

- ✓ Butler AI чат-интерфейс (Claude-powered) — existing
- ✓ ElevenLabs голосовой интерфейс — existing
- ✓ Agent SDK + Hub система (WebSocket) — existing
- ✓ AutoBidder для автоматических ставок агентов — existing
- ✓ Solana smart contracts (escrow, reputation, payments) — existing
- ✓ Developer Portal для регистрации агентов — existing
- ✓ Prisma + PostgreSQL для persistence — existing
- ✓ Stripe интеграция для USD оплаты — existing
- ✓ Marketplace UI с отображением джобов — existing

### Active

- [ ] Джоб созданный через Butler должен появляться на маркетплейсе
- [ ] Таймер биддинга (15 сек) не должен сбрасываться при новых сообщениях
- [ ] Редизайн экрана логина в мобильном приложении — аккуратные поля
- [ ] Подключение кошелька — только при оплате, два равных варианта: Stripe (USD) / кошелёк (USDC)
- [ ] Статусы джобов на маркетплейсе синхронизированы с реальными фазами (collecting bids → in progress → completed)

### Out of Scope

- Rate limiting / security hardening — не для хакатона
- Тесты — не до демо
- Webhook retry / DLQ — не влияет на демо
- Mobile app (нативная) — фокус на веб

## Context

- **Ситуация:** Хакатон, нужно отполировать проект для презентации жюри
- **Стек:** Next.js 16 (TypeScript) + Python FastAPI (Butler/Agents) + Solana/Anchor (smart contracts)
- **Деплой:** Vercel (frontend) + Railway (backend/agents/DB)
- **Критерий успеха:** Весь user flow от описания задачи до оплаты работает без багов при live demo

## Constraints

- **Timeline**: Хакатон — время ограничено, фокус на demo-critical баги
- **Scope**: Только фиксы и полировка, никаких новых фич
- **Tech stack**: Менять нельзя, только чинить существующее

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Кошелёк только при оплате, не при логине | UX — не пугать юзера web3 при входе | — Pending |
| Stripe и USDC как равные варианты оплаты | Гибкость для юзера — USD или крипто | — Pending |
| Фокус на 5 конкретных багов | Максимальный импакт для демо за минимум времени | — Pending |

---
*Last updated: 2026-03-14 after initialization*
