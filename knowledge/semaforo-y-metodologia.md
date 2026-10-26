# Cómo leer VolScan: semáforo oficial frente a índices propios

## Semáforo volcánico (oficial)
En Canarias, las alertas volcánicas a la población las gestiona el **PEVOLCA** (Gobierno de Canarias), con el asesoramiento de su comité científico (IGN, INVOLCAN y otros). Los cabildos tienen sus planes insulares (PAIV). El semáforo tiene cuatro colores (verde, amarillo, naranja y rojo), de normalidad a erupción inminente o en curso. **VolScan no emite niveles de alerta.**

## Índice de actividad anómala (VolScan)
Va de 0 a 10 y compara los últimos 7 días de cada zona con su propio año anterior (dejando 30 días de separación):
- **Tasa**: cuántos sismos más que en la línea base (0 = igual, 1 = cien veces más).
- **Energía**: energía sísmica diaria liberada frente a la línea base (log10 E = 1,5 M + 4,8).
- **Somerización**: cuántos km más superficial es la mediana de profundidad (10 km cuentan como 1).
El índice es la media de las componentes disponibles × 10. **No es una probabilidad de erupción.** Muchos enjambres no acaban en erupción (Tenerife 2004, La Palma 2017–2020).

## b-value
Pendiente de la ley de Gutenberg-Richter (Aki-Utsu, con Mc por máxima curvatura + 0,2). En zonas volcánicas, un b alto (>1,3) puede indicar fluidos o fracturación. Con menos de 50 sismos por encima de Mc no se calcula.

## Mareas y Luna
Para cada sismo, VolScan calcula la fase de la marea terrestre (ciclo de ~12,42 h) y la de la Luna, y aplica el test de Schuster. Si p < 0,05, las fases no son uniformes. Eso **no prueba causalidad**, y los enjambres inflan la significación, así que mostramos también el resultado tras desagrupar (un sismo por cada ventana de 6 h).

## Pronóstico de coladas
Es un conjunto de cientos de recorridos de máxima pendiente sobre el relieve previo, con incertidumbre en la boca, la longitud, el ancho y la viscosidad. Se reponderan con cada cartografía observada. El resultado es la **probabilidad** de cubrimiento y los cuantiles (P10/P50/P90) del tiempo de llegada a barrios y al mar. Cuando el frente se detiene durante días, la estimación de tiempo se ensancha. Así ocurrió del 22 al 26 de septiembre de 2021.
