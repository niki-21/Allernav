import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AllerNav — Agentic AI Dining Safety Assistant",
  description: "Agentic AI support for safer dining decisions using allergy fit, review evidence, and menu signals.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
