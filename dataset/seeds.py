from __future__ import annotations

SEED_COMPONENTS: list[dict[str, str]] = [
    {
        "name": "FeatureGrid",
        "file": "FeatureGrid.tsx",
        "intent": "Upgrade this feature grid with cohesive surface depth, subtle hover lift, and a staggered viewport entrance.",
        "source": """import React from 'react';

export interface FeatureItem {
  id: string;
  title: string;
  description: string;
  metric: string;
}

export interface FeatureGridProps {
  items: FeatureItem[];
  onSelect?: (id: string) => void;
}

export function FeatureGrid({ items, onSelect }: FeatureGridProps) {
  return (
    <section className="py-12 px-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {items.map((item) => (
          <div
            key={item.id}
            onClick={() => onSelect?.(item.id)}
            className="p-6 border rounded-lg cursor-pointer"
          >
            <span className="text-xs font-mono">{item.metric}</span>
            <h3 className="text-lg font-semibold mt-2">{item.title}</h3>
            <p className="text-sm mt-1">{item.description}</p>
          </div>
        ))}
      </div>
    </section>
  );
}""",
    },
    {
        "name": "PricingCard",
        "file": "PricingCard.tsx",
        "intent": "Elevate this pricing card with clear visual hierarchy, interactive CTA feedback, and reduced-motion safe entrance.",
        "source": """import React from 'react';

export interface PricingCardProps {
  tier: string;
  price: string;
  features: string[];
  highlighted?: boolean;
  onSubscribe: () => void;
}

export function PricingCard({ tier, price, features, highlighted = false, onSubscribe }: PricingCardProps) {
  return (
    <div className="p-6 border rounded-xl flex flex-col justify-between">
      <div>
        <h3 className="text-xl font-bold">{tier}</h3>
        <p className="text-3xl font-extrabold mt-3">{price}</p>
        <ul className="mt-6 space-y-2">
          {features.map((feat) => (
            <li key={feat} className="text-sm">{feat}</li>
          ))}
        </ul>
      </div>
      <button
        type="button"
        onClick={onSubscribe}
        className="mt-8 w-full py-2.5 px-4 rounded-lg font-medium"
      >
        Get Started
      </button>
    </div>
  );
}""",
    },
    {
        "name": "MetricHeader",
        "file": "MetricHeader.tsx",
        "intent": "Refine typography rhythm, tabular numbers, and subtle mount transition while keeping all props intact.",
        "source": """import React from 'react';

export interface MetricHeaderProps {
  title: string;
  subtitle: string;
  activeUsers: number;
  deltaPercent: string;
}

export function MetricHeader({ title, subtitle, activeUsers, deltaPercent }: MetricHeaderProps) {
  return (
    <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 p-6 border-b">
      <div>
        <h1 className="text-2xl font-bold">{title}</h1>
        <p className="text-sm mt-1">{subtitle}</p>
      </div>
      <div className="flex items-baseline gap-3">
        <span className="text-3xl font-bold">{activeUsers.toLocaleString()}</span>
        <span className="text-xs px-2 py-0.5 rounded">{deltaPercent}</span>
      </div>
    </header>
  );
}""",
    },
    {
        "name": "StickyNavbar",
        "file": "StickyNavbar.tsx",
        "intent": "Style this navigation bar with backdrop blur, hairline border, and smooth active tab indicator transitions.",
        "source": """import React from 'react';

export interface NavLinkItem {
  label: string;
  href: string;
}

export interface StickyNavbarProps {
  brand: string;
  links: NavLinkItem[];
  activeHref: string;
  onNavigate: (href: string) => void;
}

export function StickyNavbar({ brand, links, activeHref, onNavigate }: StickyNavbarProps) {
  return (
    <nav className="sticky top-0 z-40 w-full border-b px-6 py-3 flex items-center justify-between">
      <span className="font-bold text-lg">{brand}</span>
      <div className="flex items-center gap-2">
        {links.map((link) => (
          <button
            key={link.href}
            type="button"
            onClick={() => onNavigate(link.href)}
            className={`px-3 py-1.5 rounded-md text-sm ${activeHref === link.href ? 'font-semibold' : ''}`}
          >
            {link.label}
          </button>
        ))}
      </div>
    </nav>
  );
}""",
    },
    {
        "name": "BentoOverview",
        "file": "BentoOverview.tsx",
        "intent": "Transform this bento layout with layered card surfaces, inner rim highlights, and staggered scroll reveal.",
        "source": """import React from 'react';

export interface BentoTile {
  id: string;
  label: string;
  value: string;
  span?: 'wide' | 'normal';
}

export interface BentoOverviewProps {
  tiles: BentoTile[];
}

export function BentoOverview({ tiles }: BentoOverviewProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-6">
      {tiles.map((tile) => (
        <div
          key={tile.id}
          className={`p-5 border rounded-xl ${tile.span === 'wide' ? 'md:col-span-2' : ''}`}
        >
          <p className="text-xs uppercase tracking-wider">{tile.label}</p>
          <p className="text-2xl font-bold mt-2">{tile.value}</p>
        </div>
      ))}
    </div>
  );
}""",
    },
    {
        "name": "MediaGalleryCard",
        "file": "MediaGalleryCard.tsx",
        "intent": "Upgrade this visual discovery card with GPU-safe image zoom on hover, overlay gradient, and crisp action button feedback.",
        "source": """import React from 'react';

export interface MediaGalleryCardProps {
  id: string;
  imageUrl: string;
  title: string;
  author: string;
  saved: boolean;
  onToggleSave: (id: string) => void;
}

export function MediaGalleryCard({ id, imageUrl, title, author, saved, onToggleSave }: MediaGalleryCardProps) {
  return (
    <article className="group relative overflow-hidden rounded-xl border">
      <img src={imageUrl} alt={title} className="w-full h-64 object-cover" />
      <div className="p-4 flex items-center justify-between">
        <div>
          <h4 className="font-medium text-sm">{title}</h4>
          <p className="text-xs">{author}</p>
        </div>
        <button
          type="button"
          onClick={() => onToggleSave(id)}
          className="px-3 py-1 text-xs rounded-md border"
        >
          {saved ? 'Saved' : 'Save'}
        </button>
      </div>
    </article>
  );
}""",
    },
    {
        "name": "CommandPaletteModal",
        "file": "CommandPaletteModal.tsx",
        "intent": "Add tactile backdrop fade, spring scale entrance, and keyboard-accessible item hover states while preserving filter logic.",
        "source": """import React, { useState } from 'react';

export interface CommandAction {
  id: string;
  label: string;
  shortcut?: string;
}

export interface CommandPaletteModalProps {
  open: boolean;
  actions: CommandAction[];
  onSelect: (id: string) => void;
  onClose: () => void;
}

export function CommandPaletteModal({ open, actions, onSelect, onClose }: CommandPaletteModalProps) {
  const [query, setQuery] = useState('');
  if (!open) return null;

  const filtered = actions.filter((a) => a.label.toLowerCase().includes(query.toLowerCase()));

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-24 p-4" onClick={onClose}>
      <div className="w-full max-w-lg rounded-xl border p-4" onClick={(e) => e.stopPropagation()}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Type a command..."
          className="w-full px-3 py-2 rounded-md border text-sm"
        />
        <ul className="mt-3 divide-y">
          {filtered.map((action) => (
            <li key={action.id}>
              <button
                type="button"
                onClick={() => onSelect(action.id)}
                className="w-full flex items-center justify-between px-3 py-2 text-sm text-left"
              >
                <span>{action.label}</span>
                {action.shortcut && <kbd className="text-xs">{action.shortcut}</kbd>}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}""",
    },
    {
        "name": "TabsSwitcher",
        "file": "TabsSwitcher.tsx",
        "intent": "Elevate this tab bar with smooth active pill transitions, crisp typography contrast, and reduced-motion compliance.",
        "source": """import React from 'react';

export interface TabOption {
  id: string;
  label: string;
}

export interface TabsSwitcherProps {
  tabs: TabOption[];
  activeTab: string;
  onChange: (id: string) => void;
}

export function TabsSwitcher({ tabs, activeTab, onChange }: TabsSwitcherProps) {
  return (
    <div role="tablist" className="inline-flex p-1 rounded-lg border gap-1">
      {tabs.map((tab) => {
        const isActive = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            role="tab"
            aria-selected={isActive}
            type="button"
            onClick={() => onChange(tab.id)}
            className={`px-3.5 py-1.5 text-sm rounded-md ${isActive ? 'font-semibold' : ''}`}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}""",
    },
    {
        "name": "HeroSplit",
        "file": "HeroSplit.tsx",
        "intent": "Upgrade this hero section with high-craft display typography, layered preview card framing, and choreographed mount sequence.",
        "source": """import React from 'react';

export interface HeroSplitProps {
  badge: string;
  headline: string;
  subheadline: string;
  primaryLabel: string;
  onPrimaryClick: () => void;
  previewImage: string;
}

export function HeroSplit({
  badge,
  headline,
  subheadline,
  primaryLabel,
  onPrimaryClick,
  previewImage,
}: HeroSplitProps) {
  return (
    <section className="max-w-6xl mx-auto px-6 py-16 grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
      <div>
        <span className="inline-block text-xs font-medium px-3 py-1 rounded-full border">{badge}</span>
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight mt-4">{headline}</h1>
        <p className="text-base mt-4 leading-relaxed">{subheadline}</p>
        <button
          type="button"
          onClick={onPrimaryClick}
          className="mt-8 px-6 py-3 rounded-lg font-semibold text-sm"
        >
          {primaryLabel}
        </button>
      </div>
      <div className="rounded-2xl border p-2">
        <img src={previewImage} alt={headline} className="w-full rounded-xl object-cover" />
      </div>
    </section>
  );
}""",
    },
    {
        "name": "ActivityFeed",
        "file": "ActivityFeed.tsx",
        "intent": "Refine this activity timeline with subtle row hover highlights, tabular timestamps, and staggered list entrance.",
        "source": """import React from 'react';

export interface ActivityEvent {
  id: string;
  actor: string;
  action: string;
  timestamp: string;
}

export interface ActivityFeedProps {
  events: ActivityEvent[];
}

export function ActivityFeed({ events }: ActivityFeedProps) {
  return (
    <div className="rounded-xl border p-5">
      <h2 className="text-base font-semibold mb-4">Recent Activity</h2>
      <ul className="space-y-3">
        {events.map((ev) => (
          <li key={ev.id} className="flex items-center justify-between text-sm py-2 px-3 rounded-lg">
            <div>
              <span className="font-medium">{ev.actor}</span>{' '}
              <span>{ev.action}</span>
            </div>
            <time className="text-xs font-mono">{ev.timestamp}</time>
          </li>
        ))}
      </ul>
    </div>
  );
}""",
    },
]
