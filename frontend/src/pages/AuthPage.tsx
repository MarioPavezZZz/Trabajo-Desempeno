/**
 * Inicio de sesión y registro (una página, dos modos).
 * Tras entrar, vuelve a la página indicada en `?volver=` (por ejemplo el
 * carrito) o a "Mi cuenta".
 */
import { type FormEvent, useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { usePageView } from "../analytics";
import { errorMessage } from "../lib/api";
import { useAuthActions, useMe } from "../lib/session";

const inputClass =
  "mt-1 w-full rounded-sm border border-felt-line bg-felt px-3 py-2 text-ivory placeholder:text-ivory-dim focus:border-brass";

/** Solo se permite volver a rutas internas (evita redirecciones a otros sitios). */
function safeReturn(value: string | null): string {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : "/cuenta";
}

export default function AuthPage({ mode }: { mode: "login" | "register" }) {
  const isLogin = mode === "login";
  const [params] = useSearchParams();
  const back = safeReturn(params.get("volver"));
  const navigate = useNavigate();
  const { data: me } = useMe();
  const { login, register } = useAuthActions();
  const action = isLogin ? login : register;
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });

  usePageView(`${isLogin ? "Ingresar" : "Crear cuenta"} | TCGMASTER`);
  useEffect(() => {
    // Al cambiar entre "Ingresar" y "Crear cuenta" se limpia el error anterior.
    login.reset();
    register.reset();
  }, [isLogin]); // las mutaciones se recrean en cada render; solo importa el modo

  if (me) return <Navigate to={back} replace />;

  function submit(event: FormEvent) {
    event.preventDefault();
    const onSuccess = () => navigate(back, { replace: true });
    if (isLogin) login.mutate({ email: form.email, password: form.password }, { onSuccess });
    else register.mutate(form, { onSuccess });
  }

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [key]: e.target.value });
  const otherLink = `${isLogin ? "/cuenta/registro" : "/cuenta/ingresar"}${back !== "/cuenta" ? `?volver=${encodeURIComponent(back)}` : ""}`;

  return (
    <div className="mx-auto max-w-md px-4 py-16 sm:px-6">
      <h1 className="font-display text-3xl">{isLogin ? "Ingresar" : "Crear cuenta"}</h1>
      <p className="mt-2 text-ivory-dim">
        {isLogin
          ? "Entra para ver tu carrito guardado y tus pedidos."
          : "Con una cuenta, tu carrito queda guardado en cualquier dispositivo."}
      </p>

      <form onSubmit={submit} className="mt-8 space-y-5" noValidate={false}>
        {!isLogin && (
          <div>
            <label htmlFor="nombre" className="text-sm font-semibold">Nombre</label>
            <input id="nombre" required minLength={2} maxLength={120} autoComplete="name" value={form.full_name} onChange={set("full_name")} className={inputClass} />
          </div>
        )}
        <div>
          <label htmlFor="correo" className="text-sm font-semibold">Correo</label>
          <input id="correo" type="email" required autoComplete="email" value={form.email} onChange={set("email")} className={inputClass} />
        </div>
        <div>
          <label htmlFor="clave" className="text-sm font-semibold">Contraseña</label>
          <input
            id="clave"
            type="password"
            required
            minLength={isLogin ? 1 : 8}
            maxLength={72}
            autoComplete={isLogin ? "current-password" : "new-password"}
            aria-describedby={isLogin ? undefined : "clave-ayuda"}
            value={form.password}
            onChange={set("password")}
            className={inputClass}
          />
          {!isLogin && <p id="clave-ayuda" className="mt-1 text-xs text-ivory-dim">Al menos 8 caracteres.</p>}
        </div>

        {action.isError && (
          <p role="alert" className="rounded-sm border border-cond-hp px-3 py-2 text-sm text-cond-hp">
            {errorMessage(action.error)}
          </p>
        )}

        <button
          type="submit"
          disabled={action.isPending}
          className="w-full rounded-sm bg-brass py-2.5 font-semibold text-felt hover:bg-brass-bright disabled:opacity-60"
        >
          {action.isPending ? (isLogin ? "Ingresando…" : "Creando cuenta…") : isLogin ? "Ingresar" : "Crear cuenta"}
        </button>
      </form>

      <p className="mt-6 text-sm text-ivory-dim">
        {isLogin ? "¿No tienes cuenta? " : "¿Ya tienes cuenta? "}
        <Link to={otherLink} className="font-semibold text-brass hover:text-brass-bright">
          {isLogin ? "Crear una cuenta" : "Ingresar"}
        </Link>
      </p>
    </div>
  );
}
