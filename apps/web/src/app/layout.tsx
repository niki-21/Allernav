import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Allernav",
  description: "Search restaurants by allergy fit, review evidence, and trust-backed safety signals.",
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
