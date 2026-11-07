"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Users, Images, Server, Drama, Cloud, ClipboardCheck,
} from "lucide-react";
import { clsx } from "clsx";

// Exibe apenas telas que já existem no painel; as demais entram conforme forem implementadas.
const ITEMS = [
  { href: "/", label: "Visão geral", icon: LayoutDashboard },
  { href: "/contas", label: "Contas", icon: Users },
  { href: "/personas", label: "Personas", icon: Drama },
  { href: "/servidores", label: "Servidores", icon: Server },
  { href: "/integracoes/appruncloud", label: "AppRunCloud", icon: Cloud },
  { href: "/revisoes", label: "Revisões", icon: ClipboardCheck },
  { href: "/midias", label: "Mídias", icon: Images },
];

export function Nav() {
  const pathname = usePathname();
  if (pathname === "/login") return null;

  return (
    <nav className="w-full shrink-0 border-b border-surface-border bg-surface-raised/40 p-3 md:w-56 md:border-b-0 md:border-r">
      <div className="mb-2 px-2 pt-1 md:mb-6 md:pt-2">
        <span className="text-lg font-semibold tracking-tight text-slate-100">
          🏛️ Olimpo
        </span>
      </div>

      <ul className="flex gap-1 overflow-x-auto pb-1 md:block md:space-y-0.5 md:overflow-visible md:pb-0">
        {ITEMS.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
          return (
            <li key={href}>
              <Link
                href={href}
                className={clsx(
                  "flex shrink-0 items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors md:w-full",
                  active
                    ? "bg-surface-border/60 font-medium text-slate-100"
                    : "text-slate-400 hover:bg-surface-border/30 hover:text-slate-200",
                )}
              >
                <Icon size={16} strokeWidth={1.75} />
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

