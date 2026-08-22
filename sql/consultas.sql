-- =====================================================================
-- MAI · Mesa de Ayuda Inteligente — consultas de la etapa 1
--
-- Escritas en SQL portable: se verificaron ejecutándolas sobre el
-- esquema entregado, sin modificarlo. No usan funciones propias de un
-- motor, salvo donde se indica explícitamente en un comentario.
--
-- Todas las consultas parametrizables usan marcadores (?) y nunca
-- concatenación. Ver §5.2 de CLAUDE.md: interpolar un valor en una
-- consulta es la vía de la inyección SQL, y con el operador % de Python
-- parece parametrizado sin serlo.
-- =====================================================================


-- ---------------------------------------------------------------------
-- C1 · Agregación por área
--
-- Volumen, reparto abierto/cerrado y tasa de reapertura por área.
--
-- El 100.0 del cálculo de la tasa no es adorno: fuerza división en punto
-- flotante. Con enteros, 5/120 daría 0 en varios motores.
--
-- COUNT(*) nunca es cero dentro de un GROUP BY —el grupo existe porque
-- hay al menos una fila— así que aquí no hay riesgo de división por
-- cero. Un área sin tickets simplemente no aparece.
-- ---------------------------------------------------------------------
SELECT
    a.nombre                                                   AS area,
    a.sede                                                     AS sede,
    COUNT(*)                                                   AS total_tickets,
    SUM(CASE WHEN t.estado = 'Cerrado' THEN 1 ELSE 0 END)      AS cerrados,
    SUM(CASE WHEN t.estado <> 'Cerrado' THEN 1 ELSE 0 END)     AS abiertos,
    SUM(CASE WHEN t.reaperturas > 0 THEN 1 ELSE 0 END)         AS con_reapertura,
    ROUND(
        100.0 * SUM(CASE WHEN t.reaperturas > 0 THEN 1 ELSE 0 END) / COUNT(*),
        2
    )                                                          AS tasa_reapertura_pct
FROM tickets t
JOIN areas a ON a.id_area = t.id_area
GROUP BY a.id_area, a.nombre, a.sede
ORDER BY total_tickets DESC, area;

-- Nota sobre el tiempo promedio de atención: se dejó fuera a propósito.
-- Calcular días entre dos fechas no es portable —MySQL usa
-- DATEDIFF(fecha_cierre, fecha_creacion), SQLite JULIANDAY(...) - JULIANDAY(...),
-- Oracle una resta directa— y no se quiso atar el entregable a un motor.
-- Ese cálculo ya está resuelto en el pipeline de Python, sobre datos limpios.


-- ---------------------------------------------------------------------
-- C2 · Join de tres tablas: tickets + usuarios + areas
--
-- Detalle del ticket con el nombre del solicitante y el área asignada.
--
-- Un ticket guarda DOS referencias de área: la suya (tickets.id_area,
-- el área que atiende) y la de quien lo radicó (usuarios.id_area). No
-- tienen por qué coincidir, y cuándo no coinciden es información útil:
-- indica trabajo que un área hace para otra. La columna
-- solicitante_de_otra_area lo marca en vez de esconderlo.
-- ---------------------------------------------------------------------
SELECT
    t.codigo                                     AS ticket,
    t.estado                                     AS estado,
    t.prioridad                                  AS prioridad,
    t.categoria                                  AS categoria,
    t.fecha_creacion                             AS creado,
    u.nombre                                     AS solicitante,
    u.correo                                     AS correo_solicitante,
    a_atiende.nombre                             AS area_que_atiende,
    a_solicita.nombre                            AS area_del_solicitante,
    CASE WHEN u.id_area <> t.id_area THEN 'SI' ELSE 'NO' END
                                                 AS solicitante_de_otra_area
FROM tickets t
JOIN usuarios u          ON u.id_usuario = t.id_usuario
JOIN areas    a_atiende  ON a_atiende.id_area  = t.id_area
JOIN areas    a_solicita ON a_solicita.id_area = u.id_area
WHERE t.estado <> 'Cerrado'
ORDER BY t.fecha_creacion DESC;

-- Variante parametrizada, para cuando se filtre por área desde la
-- aplicación. El marcador va SIEMPRE así, nunca concatenado:
--
--   ... WHERE t.id_area = ? AND t.estado <> 'Cerrado' ...


-- ---------------------------------------------------------------------
-- C3 · Tickets reabiertos — y la discrepancia entre las dos fuentes
--
-- Hay dos formas de saber si un ticket se reabrió, y NO dan lo mismo:
--
--   a) el contador tickets.reaperturas
--   b) los eventos historial_estado.estado_nuevo = 'Reabierto'
--
-- Medido sobre los datos entregados: 36 tickets tienen contador > 0,
-- pero solo 28 tienen algún evento de reapertura, y 27 de los 120
-- discrepan entre ambas fuentes.
--
-- Esta consulta no elige una y esconde la otra: devuelve las dos y marca
-- la diferencia. Un informe que reporte «36 reabiertos» y otro que
-- reporte «28» son ambos defendibles; lo que no es defendible es no
-- saber cuál se está reportando.
--
-- El LEFT JOIN es deliberado: con JOIN a secas desaparecerían los
-- tickets que tienen contador pero ningún evento — justo los que
-- interesa ver.
-- ---------------------------------------------------------------------
SELECT
    t.codigo                                          AS ticket,
    a.nombre                                          AS area,
    t.estado                                          AS estado_actual,
    t.reaperturas                                     AS contador_reaperturas,
    COUNT(h.id_historial)                             AS eventos_de_reapertura,
    CASE
        WHEN t.reaperturas <> COUNT(h.id_historial) THEN 'DISCREPA'
        ELSE 'OK'
    END                                               AS concordancia,
    MAX(h.fecha_cambio)                               AS ultima_reapertura
FROM tickets t
JOIN areas a ON a.id_area = t.id_area
LEFT JOIN historial_estado h
       ON h.id_ticket = t.id_ticket
      AND h.estado_nuevo = 'Reabierto'
GROUP BY t.id_ticket, t.codigo, a.nombre, t.estado, t.reaperturas
HAVING t.reaperturas > 0 OR COUNT(h.id_historial) > 0
ORDER BY t.reaperturas DESC, eventos_de_reapertura DESC, ticket;


-- =====================================================================
-- ÍNDICES PROPUESTOS
--
-- El esquema entregado no trae ninguno a propósito y pide proponerlos.
-- Cada uno responde a un acceso concreto de las consultas de arriba o
-- del pipeline, no a "por si acaso". Un índice no es gratis: ocupa
-- espacio y encarece cada INSERT y UPDATE de la tabla.
--
-- A esta escala —120 tickets de prueba— ninguno cambia nada medible.
-- Se proponen pensando en el volumen real que declara el negocio:
-- 3.000 solicitudes diarias, cerca de 1,1 millones al año.
-- =====================================================================

-- Las claves foráneas se usan en todos los JOIN de arriba. En MySQL con
-- InnoDB el índice de la FK se crea solo; en otros motores no, y en
-- SQLite nunca. Se declaran explícitamente para no depender de eso.
CREATE INDEX idx_tickets_area            ON tickets(id_area);
CREATE INDEX idx_tickets_usuario         ON tickets(id_usuario);
CREATE INDEX idx_adjuntos_ticket         ON adjuntos(id_ticket);
CREATE INDEX idx_historial_ticket        ON historial_estado(id_ticket);

-- El informe mensual filtra por rango de fecha de creación: es el acceso
-- más frecuente del sistema y hoy obliga a recorrer la tabla completa.
CREATE INDEX idx_tickets_fecha_creacion  ON tickets(fecha_creacion);

-- Índice compuesto para el listado con filtros de la API (etapa 2):
-- área + estado + fecha. El orden de las columnas importa: primero la de
-- mayor selectividad y la que siempre aparece en el filtro. Un índice
-- (estado, id_area) no serviría para una consulta que filtra solo por
-- área, pero (id_area, estado) sí sirve para una que filtra solo por área.
CREATE INDEX idx_tickets_area_estado_fecha
    ON tickets(id_area, estado, fecha_creacion);

-- C3 recorre el historial buscando un estado concreto por ticket.
CREATE INDEX idx_historial_ticket_estado ON historial_estado(id_ticket, estado_nuevo);

-- No se indexa: categoria, prioridad ni canal. Tienen muy pocos valores
-- distintos (12, 4 y 4), así que el índice apenas descarta filas y el
-- motor terminaría ignorándolo. Indexar una columna de baja cardinalidad
-- es coste de escritura sin beneficio de lectura.
