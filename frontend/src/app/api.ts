/**
 * Cliente de la API de MAI.
 *
 * La URL base se resuelve en tiempo de ejecución y no al compilar, para que el
 * mismo paquete sirva en varios ambientes: recompilar para cambiar una URL es
 * lo que produce «funciona en mi máquina».
 *
 * Se busca en tres sitios, en este orden:
 *
 * 1. `window.MAI_API`, que define `index.html` — es lo que se sobrescribe al
 *    desplegar, inyectando otro valor antes de que cargue la aplicación.
 * 2. `localStorage.MAI_API`, para desarrollo. **Sobrevive a la recarga**, que
 *    es la diferencia que importa: asignar `window.MAI_API` desde la consola
 *    no sirve de nada, porque la recarga destruye la variable y sin recargar
 *    esta clase ya leyó su valor.
 * 3. El puerto documentado en el README.
 *
 * El paso 2 existe porque el puerto por defecto puede estar ocupado por otro
 * servicio de la máquina, y entonces las instrucciones del README no llevan a
 * ninguna parte. Se resuelve así y no con un parámetro en la URL a propósito:
 * una dirección tomada de la barra del navegador es una dirección que puede
 * poner un tercero en un enlace.
 */
import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, throwError } from 'rxjs';

/** Una solicitud tal como la devuelve la API. */
export interface Solicitud {
  codigo: string;
  asunto: string;
  descripcion: string;
  area: string;
  solicitante: string;
  canal: string;
  categoria: string;
  prioridad: string;
  estado: string;
  fecha_creacion: string;
  /** «modelo» o «degradado». Ver el comentario de `esDegradada` en la pantalla. */
  origen_clasificacion: string;
  confianza: string;
  motivo_degradacion: string | null;
}

export interface Listado {
  datos: Solicitud[];
  total: number;
  limite: number;
  desplazamiento: number;
}

/** La forma uniforme de error de la API. Todos los errores la tienen. */
export interface ErrorDeApi {
  codigo: string;
  mensaje: string;
  detalle: Record<string, unknown>;
  id_traza: string;
}

export interface Filtros {
  area?: string;
  estado?: string;
  categoria?: string;
  prioridad?: string;
  limite?: number;
  desplazamiento?: number;
}

declare global {
  interface Window {
    MAI_API?: string;
  }
}

@Injectable({ providedIn: 'root' })
export class Api {
  private readonly http = inject(HttpClient);
  /** Pública para que el mensaje de error pueda decir contra qué intentó. */
  readonly base = Api.resolverBase();

  /** Ver la cabecera del archivo: window → localStorage → valor por defecto. */
  private static resolverBase(): string {
    if (window.MAI_API) return window.MAI_API;
    try {
      const guardada = window.localStorage.getItem('MAI_API');
      if (guardada) return guardada;
    } catch {
      // localStorage puede estar bloqueado por la configuración del navegador.
      // No es motivo para que la aplicación no arranque: se usa el valor por
      // defecto y se sigue.
    }
    return 'http://127.0.0.1:8000';
  }

  listar(filtros: Filtros): Observable<Listado> {
    // Un filtro vacío NO se envía. Mandarlo como cadena vacía haría que la
    // API lo tratara como un valor a validar y respondiera 422 — el filtro
    // ausente y el filtro vacío son cosas distintas para el servidor.
    let parametros = new HttpParams();
    for (const [clave, valor] of Object.entries(filtros)) {
      if (valor !== undefined && valor !== null && `${valor}`.trim() !== '') {
        parametros = parametros.set(clave, `${valor}`);
      }
    }

    return this.http
      .get<Listado>(`${this.base}/solicitudes`, { params: parametros })
      .pipe(catchError((error) => throwError(() => this.traducir(error))));
  }

  /**
   * Traduce el error HTTP al mensaje que verá una persona.
   *
   * Se distingue el caso de red del caso de respuesta: «no se pudo conectar»
   * y «el servidor rechazó los filtros» exigen acciones opuestas de quien lo
   * lee, y mostrar «Error» para los dos no ayuda a ninguno.
   */
  private traducir(error: HttpErrorResponse): ErrorDeApi {
    if (error.status === 0) {
      return {
        codigo: 'SIN_CONEXION',
        mensaje:
          'No se pudo conectar con la API. Verifique que esté levantada y que ' +
          'MAI_ORIGENES_PERMITIDOS incluya el origen de esta página.',
        detalle: {},
        id_traza: '',
      };
    }
    const cuerpo = error.error as Partial<ErrorDeApi> | null;
    return {
      codigo: cuerpo?.codigo ?? 'ERROR_DESCONOCIDO',
      mensaje: cuerpo?.mensaje ?? `El servidor respondió ${error.status}.`,
      detalle: cuerpo?.detalle ?? {},
      id_traza: cuerpo?.id_traza ?? '',
    };
  }
}
