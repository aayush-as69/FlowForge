import "./globals.css";

export const metadata = {
  title: "FlowForge — Automate the function. Not just the task.",
  description:
    "AI-native automation that takes business functions from the first input to the finished outcome, while humans handle only the decisions that require judgment.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="min-h-screen font-sans">{children}</body>
    </html>
  );
}
