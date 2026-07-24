import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { AppShell } from "@/components/layout/AppShell";
import { AuthGate } from "@/components/auth/AuthGate";
import { QueryProvider } from "@/providers/query-provider";
import { AuthProvider } from "@/providers/auth-provider";

import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Spec Check",
  description: "Tender specification review — upload, extract, and verify requirements",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Applies the saved theme before first paint — without this, every
            loading state (auth check, page transitions, etc.) briefly
            renders in light mode because React hasn't mounted yet. */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "(function(){try{var t=localStorage.getItem('spec-check-theme');" +
              "if(t==='dark'){document.documentElement.dataset.theme='dark';}}catch(e){}})();",
          }}
        />
      </head>
      <body className={`${inter.variable} font-sans`}>
        <QueryProvider>
          <AuthProvider>
            <AuthGate>
              <AppShell>{children}</AppShell>
            </AuthGate>
          </AuthProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
