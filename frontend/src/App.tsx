/**
 * Rutas del sitio. Cada página se carga en un archivo aparte (code splitting),
 * así la primera visita solo descarga el código de la página que se abre.
 */
import { Suspense, lazy } from "react";
import { Route, Routes } from "react-router-dom";
import Footer from "./components/Footer";
import Header from "./components/Header";
import ScrollToTop from "./components/ScrollToTop";
// El home es la página de entrada más común: va en el paquete principal para no
// agregar una descarga extra antes del primer render (mejor LCP).
import HomePage from "./pages/HomePage";
import { SECTIONS } from "./pages/sections";

const ListingPage = lazy(() => import("./pages/ListingPage"));
const ProductPage = lazy(() => import("./pages/ProductPage"));
const AuthPage = lazy(() => import("./pages/AuthPage"));
const AccountPage = lazy(() => import("./pages/AccountPage"));
const CartPage = lazy(() => import("./pages/CartPage"));
const CheckoutPage = lazy(() => import("./pages/CheckoutPage"));
const MockPaymentPage = lazy(() => import("./pages/MockPaymentPage"));
const CheckoutResultPage = lazy(() => import("./pages/CheckoutResultPage"));
const NotFoundPage = lazy(() => import("./pages/NotFoundPage"));

export default function App() {
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#contenido"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:bg-brass focus:px-3 focus:py-2 focus:text-felt"
      >
        Ir al contenido
      </a>
      <ScrollToTop />
      <Header />
      <main id="contenido" className="flex-1">
        {/* Mientras llega el código de una página se reserva la pantalla completa:
            así el pie no aparece arriba para luego saltar (CLS). */}
        <Suspense fallback={<div className="min-h-screen" />}>
          <Routes>
            <Route path="/" element={<HomePage />} />
            {SECTIONS.map((s) => (
              <Route key={s.path} path={s.path} element={<ListingPage section={s} />} />
            ))}
            <Route path="/producto/:slug" element={<ProductPage />} />
            <Route path="/cuenta" element={<AccountPage />} />
            <Route path="/cuenta/ingresar" element={<AuthPage mode="login" />} />
            <Route path="/cuenta/registro" element={<AuthPage mode="register" />} />
            <Route path="/carrito" element={<CartPage />} />
            <Route path="/checkout" element={<CheckoutPage />} />
            <Route path="/checkout/simulado" element={<MockPaymentPage />} />
            <Route path="/checkout/resultado/:transactionId" element={<CheckoutResultPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Suspense>
      </main>
      <Footer />
    </div>
  );
}
