import type { Metadata } from "next";
import { Archivo } from "next/font/google";
import "./globals.css";

const archivo = Archivo({
  subsets: ["latin"],
  axes: ["wdth"],
  variable: "--fonte-archivo",
});

export const metadata: Metadata = {
  title: "Radar ENEM — sua nota conta, o contexto revela",
  description:
    "Descubra o que sua nota do ENEM significa comparada a quem fez a prova nas mesmas condições que você.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" className={archivo.variable}>
      <body>{children}</body>
    </html>
  );
}
