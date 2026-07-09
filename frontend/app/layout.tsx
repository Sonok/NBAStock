import type { Metadata } from "next";
import localFont from "next/font/local";
import Nav from "@/components/Nav";
import Ticker from "@/components/Ticker";
import "./globals.css";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "NBAStock — Trade the League",
  description: "A stock market for NBA players. Prices driven by real performance, popularity, and team strength.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} antialiased`}>
        <Nav />
        <Ticker />
        {children}
      </body>
    </html>
  );
}
