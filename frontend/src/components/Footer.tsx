/**
 * Pie de página con datos de la tienda y créditos de las fuentes de datos.
 */
export default function Footer() {
  return (
    <footer className="mt-20 border-t border-felt-line bg-felt-deep">
      <div className="mx-auto grid max-w-shop gap-8 px-4 py-10 text-sm text-ivory-dim sm:grid-cols-3 sm:px-6">
        <div>
          <p className="font-display text-lg text-ivory">
            TCG<span className="text-brass">MASTER</span>
          </p>
          <p className="mt-2 max-w-xs">Tienda de cartas coleccionables. Precios en pesos chilenos, IVA incluido.</p>
        </div>
        <div>
          <p className="font-semibold text-ivory">Proyecto académico</p>
          <p className="mt-2 max-w-xs">
            Sitio de prueba del curso INFB8091 Desempeño de Sistemas (UTEM). No se realizan ventas reales.
          </p>
          <p className="mt-2 max-w-xs">Este sitio usa Google Analytics para medir uso y desempeño.</p>
        </div>
        <div>
          <p className="font-semibold text-ivory">Datos e imágenes</p>
          <p className="mt-2 max-w-xs">
            Cartas obtenidas de Scryfall, TCGdex y YGOPRODeck. Las marcas pertenecen a sus respectivos dueños.
          </p>
        </div>
      </div>
    </footer>
  );
}
