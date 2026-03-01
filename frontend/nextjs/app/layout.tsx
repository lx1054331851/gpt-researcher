import type { Metadata } from "next";
import { Lexend } from "next/font/google";
import PlausibleProvider from "next-plausible";
import { GoogleAnalytics } from '@next/third-parties/google'
import { ResearchHistoryProvider } from "@/hooks/ResearchHistoryContext";
import AppI18nProvider from "@/components/i18n/AppI18nProvider";
import { headers, cookies } from "next/headers";
import { resolveInitialLocale } from "@/i18n/locale";
import { type AppLocale } from "@/i18n/constants";
import enMessages from "@/messages/en.json";
import zhCNMessages from "@/messages/zh-CN.json";
import "./globals.css";

const inter = Lexend({ subsets: ["latin"] });

const LOCALIZED_METADATA = {
  en: {
    title: enMessages.metadata.title,
    description: enMessages.metadata.description,
    siteName: enMessages.metadata.appName,
    ogLocale: "en_US",
  },
  "zh-CN": {
    title: zhCNMessages.metadata.title,
    description: zhCNMessages.metadata.description,
    siteName: zhCNMessages.metadata.appName,
    ogLocale: "zh_CN",
  },
} as const;

const url = "https://github.com/assafelovic/gpt-researcher";
const ogimage = "/favicon.ico";

const MESSAGES_BY_LOCALE = {
  en: enMessages,
  "zh-CN": zhCNMessages,
};

function getInitialLocaleFromRequest(): AppLocale {
  const cookieStore = cookies();
  const headerStore = headers();
  const cookieLocale = cookieStore.get("gptr_locale")?.value;
  const acceptLanguage = headerStore.get("accept-language");
  return resolveInitialLocale({ cookieLocale, acceptLanguage });
}

export async function generateMetadata(): Promise<Metadata> {
  const locale = getInitialLocaleFromRequest();
  const localeMetadata = LOCALIZED_METADATA[locale];

  return {
    metadataBase: new URL(url),
    title: localeMetadata.title,
    description: localeMetadata.description,
    manifest: '/manifest.json',
    icons: {
      icon: "/img/gptr-black-logo.png",
      apple: '/img/gptr-black-logo.png',
    },
    appleWebApp: {
      capable: true,
      statusBarStyle: 'default',
      title: localeMetadata.title,
    },
    openGraph: {
      images: [ogimage],
      title: localeMetadata.title,
      description: localeMetadata.description,
      url: url,
      siteName: localeMetadata.siteName,
      locale: localeMetadata.ogLocale,
      type: "website",
    },
    twitter: {
      card: "summary_large_image",
      images: [ogimage],
      title: localeMetadata.title,
      description: localeMetadata.description,
    },
    viewport: {
      width: 'device-width',
      initialScale: 1,
      maximumScale: 1,
      userScalable: false,
    },
    themeColor: '#111827',
  };
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const initialLocale = getInitialLocaleFromRequest();
  const initialMessages = MESSAGES_BY_LOCALE[initialLocale];

  return (
    <html className="gptr-root" lang={initialLocale} suppressHydrationWarning>
      <head>
        <PlausibleProvider domain="localhost:3000" />
        <GoogleAnalytics gaId={process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID!} />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="default" />
        <link rel="apple-touch-icon" href="/img/gptr-black-logo.png" />
      </head>
      <body
        className={`app-container ${inter.className} flex min-h-screen flex-col justify-between`}
        suppressHydrationWarning
      >
        <AppI18nProvider initialLocale={initialLocale} initialMessages={initialMessages}>
          <ResearchHistoryProvider>
            {children}
          </ResearchHistoryProvider>
        </AppI18nProvider>
      </body>
    </html>
  );
}
