import type { Metadata, Viewport } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Wine Shelf Scanner',
  description: 'Never guess at the wine shelf again. Ratings from 21 million reviews, on every bottle, instantly.',
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="font-sans bg-app-bg min-h-screen">
        {children}
      </body>
    </html>
  );
}
