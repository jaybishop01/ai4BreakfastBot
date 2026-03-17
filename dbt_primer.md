# dbt Labs Context Primer — AI for Breakfast Podcasts

This document provides context about dbt Labs for the AI podcast hosts. Use this to connect industry trends back to dbt's products, positioning, and roadmap when discussing the day's articles.

## What dbt Labs Does

dbt Labs is the company behind dbt (data build tool), the industry standard for data transformation. dbt enables analytics engineers to transform raw data in the warehouse using SQL and Python, with software engineering best practices (version control, testing, documentation, CI/CD).

## Core Products

- **dbt Core**: Open-source CLI tool for data transformation. The foundation of the dbt ecosystem with a massive community (50,000+ companies use dbt).
- **dbt Cloud**: SaaS platform for developing, deploying, and observing dbt projects. Includes IDE, job orchestration, environment management, CI/CD, and the Semantic Layer.
- **dbt Fusion**: Next-generation execution engine. Dramatically faster performance for dbt projects. Represents dbt's evolution from a transformation tool to a full data platform engine.
- **MetricFlow / dbt Semantic Layer**: The semantic layer that sits above the data warehouse and below BI and AI consumers. Enables consistent metric definitions consumed by any downstream tool (Tableau, Looker, Hex, AI agents, etc.).

## Key Positioning

- dbt is the **semantic layer** between the data warehouse and everything that consumes data (BI tools, AI/ML, operational systems, agents).
- The Semantic Layer is dbt's primary enterprise value proposition: one place to define metrics, dimensions, and business logic that every tool and team can trust.
- dbt addresses the "AI-ready data" challenge head-on. AI models and agents need trusted, well-defined, governed data. dbt provides that foundation.

## Current Roadmap Themes (2026)

- **Fusion engine**: Performance breakthrough. Makes dbt Cloud dramatically faster for enterprise-scale projects.
- **AI-ready data**: Positioning dbt as the critical infrastructure layer that makes enterprise AI initiatives actually work. AI agents need a semantic layer to query data accurately.
- **Universal Semantic Layer**: Gartner and others are recognizing semantic layers as critical infrastructure. dbt is the market leader here.
- **Governance and trust**: Column-level lineage, access controls, data contracts. Enterprise-grade trust for regulated industries.
- **Multi-engine / multi-warehouse**: dbt working across Snowflake, Databricks, BigQuery, Redshift, and more.

## Culture and Community

- Analytics engineering movement: dbt created and defined this role, which now exists at thousands of companies.
- Open-source roots: Community of 100,000+ practitioners, annual Coalesce conference, active Slack community.
- "Code over clicks" philosophy: Bringing software engineering best practices to the data world.

## Competitive Landscape

- **vs. legacy ETL** (Informatica, Talend): dbt is modern, code-first, warehouse-native. Legacy tools are slow, expensive, and don't support modern cloud architectures.
- **vs. Alteryx**: Alteryx is GUI-based, expensive, and doesn't integrate with modern data stacks. dbt is code-first, open-source foundation, and warehouse-native.
- **vs. warehouse-native features** (Snowflake Cortex, Databricks Unity Catalog): dbt is warehouse-agnostic and sits above any warehouse. Customers aren't locked into one vendor's ecosystem.

## Why This Matters for Go-to-Market

When discussing industry articles, consider:
- How does this trend create demand for better data transformation and governance?
- Does this company or industry have a "data readiness" problem that dbt solves?
- How does the Semantic Layer specifically address challenges mentioned in the article?
- Is there an AI/ML angle where dbt's trusted data layer is the missing piece?
- Does this competitive move create an opportunity or threat for dbt?
