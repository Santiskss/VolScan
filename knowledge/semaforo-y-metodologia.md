# Cómo leer VolScan: semáforo oficial frente a índices propios

## Semáforo volcánico (oficial)
En Canarias, las alertas volcánicas a la población las gestiona el **PEVOLCA** (Gobierno de Canarias), con el asesoramiento de su comité científico (IGN, INVOLCAN y otros). Los cabildos tienen sus planes insulares (PAIV). El semáforo tiene cuatro colores (verde, amarillo, naranja y rojo), de normalidad a erupción inminente o en curso. **VolScan no emite niveles de alerta.**

## Índice de actividad anómala (VolScan)
Va de 0 a 10 y compara los últimos 7 días de cada zona con su propio año anterior (dejando 30 días de separación). Solo cuenta los sismos por encima de la **magnitud de completitud común** (Mc por máxima curvatura sobre ambos periodos), para que una red más densa no parezca más actividad:
- **Tasa**: lo improbable del número de sismos de la semana con la tasa de la línea base (prueba de Poisson): 0 si es normal, 1 si la probabilidad es de 1 entre 10.000 millones.
- **Energía**: energía sísmica de la semana frente a la semana más energética del año anterior (0 = igual, 1 = cien veces más).
- **Somerización**: cuántos km más superficial es la mediana de profundidad (10 km cuentan como 1). Necesita 20 sismos localizados en cada periodo.
Tasa y energía no puntúan con menos de 5 sismos por encima de Mc en la semana. El índice es la media de las componentes disponibles × 10. **No es una probabilidad de erupción.**

### Historial (2011–2026)
Calculado cada 2 días en las 7 zonas (cada isla con su mar hasta 25 km, sin solaparse). Con el índice anterior (cocientes sin Mc), hubo 84 episodios por encima de 4, la mayoría en zonas casi sin sismos. Con el actual:

| Índice ≥ | Episodios | Precedieron a una erupción | Antelación |
|---|---|---|---|
| 3 | 34 | 2 de 2 | El Hierro 80 días · La Palma 6 días |
| 4 | 15 | 2 de 2 | El Hierro 80 días · La Palma 6 días |
| 5 | 14 | 2 de 2 | El Hierro 12 días · La Palma 6 días |
| 6 | 7 | 2 de 2 | El Hierro 10 días · La Palma 6 días |
| 7 | 3 | 1 de 2 | La Palma 6 días |

Los demás episodios fueron agitación real sin erupción (enjambres profundos de La Palma 2017–2020, El Hierro 2013). Dos erupciones no bastan para calcular una probabilidad. La tabla es una tasa de referencia, y se recalcula cada semana en la pestaña «Canarias en directo».

## Deformación (GNSS)
Estaciones GNSS públicas procesadas por el Nevada Geodetic Laboratory, con la placa africana fija. Para cada estación se ajusta la tendencia de los 3 años previos y se mide cuánto se aparta la mediana de los últimos 30 días (en mm), comparado con su propia dispersión (z): |z| < 3 normal, 3–6 a vigilar, > 6 anómala. Los cambios de antena se corrigen.
- El Hierro 2011: FRON (La Frontera) estaba en nivel anómalo desde el 20 de agosto, 7 semanas antes de la erupción submarina.
- La Palma 2021: MAZO y LPAL (a 10 y 17 km) registran el hundimiento durante la erupción (MAZO −44 mm hasta diciembre), pero **no** la hinchazón previa: la midió el IGN con estaciones junto a la boca que no son públicas. Para verla hace falta un convenio con el IGN o GRAFCAN.
- La serie final llega con unas 4 semanas de retraso; VolScan muestra la fecha del último dato.

## Gases (SO2 por satélite)
SO2 visible desde el espacio sobre el archipiélago, del instrumento OMPS de la NASA (troposfera baja), en kilotoneladas por encima de 1 DU. En dos años tranquilos (2024–2026), el máximo diario fue de 0,13 kt; VolScan marca «SO2 detectado» desde 1 kt. En La Palma 2021: 0 antes del 19 de septiembre, decenas de kt durante la erupción y 0 desde mediados de diciembre. Detecta erupciones y desgasificación fuerte, no la desgasificación difusa (CO2, helio) que mide INVOLCAN en superficie, que necesitaría convenio.

## b-value
Pendiente de la ley de Gutenberg-Richter (Aki-Utsu, con Mc por máxima curvatura + 0,2). En zonas volcánicas, un b alto (>1,3) puede indicar fluidos o fracturación. Con menos de 50 sismos por encima de Mc no se calcula.

## Mareas y Luna
Para cada sismo, VolScan calcula la fase de la marea terrestre (ciclo de ~12,42 h) y la de la Luna, y aplica el test de Schuster. Si p < 0,05, las fases no son uniformes. Eso **no prueba causalidad**, y los enjambres inflan la significación, así que mostramos también el resultado tras desagrupar (un sismo por cada ventana de 6 h).

## Pronóstico de coladas
Es un conjunto de cientos de recorridos de máxima pendiente sobre el relieve previo, con incertidumbre en la boca, la longitud, el ancho y la viscosidad. Se reponderan con cada cartografía de Copernicus **ya entregada** (se supone que llega 24 h después de la imagen; Copernicus tarda entre 7 h y 48 h). El resultado es la **probabilidad** de cubrimiento y los cuantiles (P10/P50/P90) del tiempo de llegada a barrios y al mar. Cuando el frente se detiene durante días, la estimación de tiempo se ensancha. Así ocurrió del 22 al 26 de septiembre de 2021.

## Impacto con reloj y validación
El dónde lo da el conjunto de coladas; el cuánto, el ritmo de crecimiento de área de los mapas ya entregados, contado desde la fecha del último mapa. El rango P10–P90 se calibra con los errores reales de los pronósticos anteriores cuya verdad ya se conocía, y su extremo alto cubre el caso de que el 30 % del área nueva rellene el terreno cercado por la colada. En 2021, el valor real cayó dentro del rango en 67 de 83 días (81 %, para un 80 % nominal) y el total se quedó un 11 % corto.

El salto del 25–28 de octubre (unos 10 edificios por hectárea nueva, en zona muy densa) sigue fuera de rango. Probamos tres formas de pronosticar dónde va ese crecimiento (desbordamientos desde los márgenes sobre el relieve ya cubierto, cercanía a márgenes activos y relleno entre brazos de la colada). Ninguna mejoró el recuento, así que no se usan para contar. Sí se usan para la **lista de vigilancia**: los edificios cercados por la colada recogieron el 21 % adicional de lo que se perdió en las 72 h siguientes.
