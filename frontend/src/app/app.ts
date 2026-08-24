/**
 * Pantalla de listado de solicitudes con filtros.
 *
 * Es una sola pantalla a propósito: el requisito es consumir la API y mostrar
 * el listado filtrado, y añadir enrutado, estado global o una librería de
 * componentes sería resolver problemas que esta pantalla no tiene.
 *
 * Los catálogos están escritos aquí y no se piden a la API porque la API no
 * los expone hoy. Está declarado como límite en el README: duplicar una lista
 * cerrada en el cliente es deuda, y decirlo es más honesto que fingir que se
 * sincroniza sola.
 */
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Api, ErrorDeApi, Filtros, Solicitud } from './api';

const AREAS = [
  'Aplicaciones', 'Infraestructura', 'Talento Humano', 'Contabilidad',
  'Compras', 'Comercial', 'Operaciones', 'Calidad',
];
const ESTADOS = ['Abierto', 'En proceso', 'Cerrado', 'Reabierto', 'Escalado'];
const CATEGORIAS = [
  'Accesos', 'Capacitación', 'Compras', 'Hardware', 'Incidentes', 'Informes',
  'Nómina', 'Otros', 'Red', 'Software', 'Vacaciones', 'Viáticos',
];
const PRIORIDADES = ['Crítica', 'Alta', 'Media', 'Baja'];

const TAMANO_PAGINA = 20;

@Component({
  selector: 'app-root',
  imports: [FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  private readonly api = inject(Api);

  protected readonly areas = AREAS;
  protected readonly estados = ESTADOS;
  protected readonly categorias = CATEGORIAS;
  protected readonly prioridades = PRIORIDADES;

  protected readonly filtros = signal<Filtros>({ limite: TAMANO_PAGINA, desplazamiento: 0 });
  protected readonly solicitudes = signal<Solicitud[]>([]);
  protected readonly total = signal(0);
  protected readonly cargando = signal(false);
  protected readonly error = signal<ErrorDeApi | null>(null);
  protected readonly consultado = signal(false);

  protected readonly desplazamiento = computed(() => this.filtros().desplazamiento ?? 0);

  /** Cuántas de las mostradas llevan clasificación de reserva. */
  protected readonly degradadas = computed(
    () => this.solicitudes().filter((s) => this.esDegradada(s)).length,
  );

  /** Los filtros puestos, para mostrarlos como fichas retirables. */
  protected readonly activos = computed(() => {
    const f = this.filtros();
    const campos: (keyof Filtros)[] = ['area', 'estado', 'categoria', 'prioridad'];
    return campos
      .filter((c) => f[c])
      .map((c) => ({ campo: c, valor: String(f[c]) }));
  });
  protected readonly hayMas = computed(
    () => this.desplazamiento() + this.solicitudes().length < this.total(),
  );

  constructor() {
    this.buscar();
  }

  /** Aplica los filtros desde la primera página. */
  protected aplicar(): void {
    this.filtros.update((f) => ({ ...f, desplazamiento: 0 }));
    this.buscar();
  }

  protected limpiar(): void {
    this.filtros.set({ limite: TAMANO_PAGINA, desplazamiento: 0 });
    this.buscar();
  }

  protected pagina(direccion: number): void {
    const siguiente = Math.max(0, this.desplazamiento() + direccion * TAMANO_PAGINA);
    this.filtros.update((f) => ({ ...f, desplazamiento: siguiente }));
    this.buscar();
  }

  protected cambiar(campo: keyof Filtros, valor: string): void {
    this.filtros.update((f) => ({ ...f, [campo]: valor || undefined }));
  }

  /** Quita un filtro desde su ficha y vuelve a consultar. */
  protected quitar(campo: keyof Filtros): void {
    this.filtros.update((f) => ({ ...f, [campo]: undefined, desplazamiento: 0 }));
    this.buscar();
  }

  /**
   * Sufijo de clase CSS para un valor de catálogo.
   *
   * Se normaliza —minúsculas, sin tildes, espacios a guiones— porque la clase
   * viaja al CSS y «En proceso» no es un selector válido. Un valor que no esté
   * en el catálogo cae en `otro` en vez de generar una clase que no existe:
   * la tabla debe seguir legible aunque la API añada un estado mañana.
   */
  protected clave(valor: string, conocidos: readonly string[]): string {
    const normalizado = valor
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .trim()
      .replace(/\s+/g, '-');
    const permitidos = conocidos.map((v) =>
      v.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\s+/g, '-'),
    );
    return permitidos.includes(normalizado) ? normalizado : 'otro';
  }

  /**
   * Una clasificación degradada la puso una regla de reserva, no el modelo.
   * Acierta menos, y quien lea la tabla tiene que poder distinguirlo: tratar
   * las dos igual es el error más probable al integrarse con esta API.
   */
  protected esDegradada(s: Solicitud): boolean {
    return s.origen_clasificacion !== 'modelo';
  }

  private buscar(): void {
    this.cargando.set(true);
    this.error.set(null);

    this.api.listar(this.filtros()).subscribe({
      next: (listado) => {
        this.solicitudes.set(listado.datos);
        this.total.set(listado.total);
        this.cargando.set(false);
        this.consultado.set(true);
      },
      error: (fallo: ErrorDeApi) => {
        // La lista anterior se limpia: dejarla en pantalla junto a un mensaje
        // de error haría creer que esos son los resultados del filtro nuevo.
        this.solicitudes.set([]);
        this.total.set(0);
        this.error.set(fallo);
        this.cargando.set(false);
        this.consultado.set(true);
      },
    });
  }
}
