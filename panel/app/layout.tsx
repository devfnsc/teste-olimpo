import type { Metadata } from "next";
import "./globals.css";
import { Nav } from "@/components/nav";
import { SwrProvider } from "@/components/swr-provider";

export const metadata: Metadata = {
  title: "Olimpo",
  description: "Central visual do Olimpo para inventário de contas, personas e dispositivos.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" className="dark">
      <body>
        <SwrProvider>
          <div className="flex min-h-screen flex-col md:flex-row">
            <Nav />
            <main className="min-w-0 flex-1 overflow-x-hidden p-4 md:p-6">{children}</main>
          </div>
        </SwrProvider>
      </body>
    </html>
  );
}
