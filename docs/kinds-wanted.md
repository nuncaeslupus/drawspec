# What the nine kinds cannot draw

drawspec exists because 89 study diagrams were written by hand in SVG and a
human reviewing them found the same faults over and over — arrow heads with no
shaft, lines that miss their box, text outside its box, a different type size in
every figure. Those faults are what the nine kinds and the fit engine are for.

This document asks the other question. Not *are the drawings correct*, but
**could drawspec have drawn them at all**. It is an inventory of the same 89
originals against the nine kinds, and of the gap that inventory shows.

> **Where the originals are.** They are the `<svg>` blocks inline in the opos
> temario, extracted to `originals/` (gitignored — they are study material, not
> source, and they belong to the other project). `originals/index.json` carries
> each one's title, the reviewer's note, its element counts, and the kind this
> document assigns it.

---

## The count

**68 of the 89 are drawable by a kind drawspec already has. 21 are not.**

| Kind | Originals | Have it? |
|---|---:|---|
| flow | 33 | yes |
| cycle | 9 | yes |
| ~~group~~ | 6 | **now yes** |
| stack | 5 | yes |
| **matrix** | **5** | **no** |
| timeline | 4 | yes |
| tree | 4 | yes |
| columns | 4 | yes |
| pyramid | 4 | yes |
| rings | 4 | yes |
| **curve** | **3** | **no** |
| **quadrant** | **2** | **no** |
| ~~funnel~~ | 2 | **now yes** |
| *picture* | 2 | out of scope |
| chart | 1 | yes |
| **spans** | **1** | **no** |

The assignment is judgement, made by rendering all 89 and looking at them; it is
recorded per-diagram in `originals/index.json` under `wants`. The long tail is
real but it is a tail: **flow alone accounts for a third of the corpus**, and the
nine kinds between them cover more than three quarters of it.

---

## The five kinds that are missing

Ordered by how many originals need them.

### 1. ~~`group`~~ — a box that contains boxes (6) — **done**

The single largest gap, and the least exotic. A Kubernetes control plane holding
five components; *sector públic* holding three peers and a sub-frame holding two
more; a medallion architecture holding bronze, silver and gold. The container has
its own caption, it nests, and edges cross its boundary to reach what is inside.

This was probably **not a kind**, and it turned out not to be one. It is a
container over the graph kinds: a `flow` or a `tree` gains one by naming
members, and everything else about the drawing is unchanged.

It also turned out to be mostly already there. The schema had declared `groups`
since v1 and the theme had declared a dashed, unfilled `group` role since v1 —
nothing had ever drawn either. What was missing between them is
`drawspec.kinds.containers`, and three decisions it had to make:

* **Nesting is layout inside layout.** A group lays its own members out, comes
  back with an extent, and is handed to its parent's layout as one node of that
  size. So direction is chosen per level, and an edge between two buried nodes
  is *lifted* to the level that contains both — for ranking only; it is still
  drawn between the real endpoints.
* **Only leaves obstruct.** An edge that ends inside a group has to cross that
  group's border, so a frame that blocked routing would make the diagram
  undrawable rather than tidy.
* **The caption is a tab in the corner, and it does obstruct.** Centred across
  the top it is exactly where an arrow arriving from outside comes in, and the
  no-line-crosses-text rule loses. In the corner, at its own width, it is the
  one part of the top edge nothing wants — and a frame something *enters* keeps
  a rank gap under its caption so the arrow has room to turn.

See `docs/reference/flow-groups.json` for the reference drawing.

*Originals: `estado__administracion-publica`,
`tic__devops-cicd-contenedores-y-kubernetes`,
`tic__arquitectura-de-datos-dw-lake-lakehouse`,
`tic__practicas-itil-de-entrega-de-servicios`,
`tic__trabajo-documental-sharepoint-y-onedrive`,
`tic__practicas-itil-de-soporte-al-servicio`.*

### 2. `matrix` — rows against columns (5)

The shared-responsibility model: three columns (IaaS, PaaS, SaaS), a stack of
cells in each, and each cell filled to say who manages it. RAID block layouts.
The TCP/IP encapsulation bands, where each layer's row is segmented and the
segments line up down the figure.

What it needs beyond `columns`: **both** headings, cells that span more than one
row, and a fill vocabulary — which is where the theme's greyscale rule bites
hardest, because the whole point of the diagram is that two cells differ. The
reviewer's note on the original is the warning: *"the hatching is too strong and
`client` is hard to read"*. A fill that competes with the text on top of it has
failed at the only job it has.

*Originals: `tic__arquitecturas-de-seguridad-en-la-nube`,
`tic__computacion-hibrida-iaas-paas-saas`, `tic__sistemas-san-y-raid`,
`tic__tcp-ip-v4-y-mpls`, `tic__itil-v4-conceptos-y-cadena-de-valor`.*

### 3. `curve` — a shape that is not data (3)

The Gartner hype cycle, the EVM S-curves, the sprint burn-down. These look like
charts and are not: there are no numbers behind the hype cycle, only a named
shape with five labelled waypoints on it. The burn-down has two series where one
is a straight ideal and the other is the real line, each labelled where it ends.

The chart kind could grow into part of this — multiple series, a dashed series,
a label at the end of a line. The waypoint annotations and the free-form named
curve are the part it could not.

*Originals: `tic__prospeccion-de-soluciones-tic`,
`tic__pmbok-rendimiento-riesgos-y-cierre`, `barcelona__scrum-bit`.*

### 4. `quadrant` — two named axes, items placed in the plane (2)

The Thomas-Kilmann grid: cooperation against assertiveness, five named positions.
Tuckman's model on a different pair of axes. Small, self-contained, and nothing
in the nine comes close — `chart` plots series against scales, not labelled points
against named directions.

*Originals: `tic__pmbok-liderazgo-equipo-y-recursos__0` and `__1`.*

### 5. ~~`funnel`~~ — the pyramid lying down (2) — **done**

An innovation funnel with three gates; a sales funnel from lead to account. A
tapering band divided into stages, captioned at both ends, with the dividers
drawn differently from the outline.

It was as close to `pyramid` as it looked: same trapezoid, same constant
progression, turned a quarter turn. What changes is **which way the shape gives
when the text does not fit**. A pyramid narrows to its apex, so its base is what
the labels buy; a funnel narrows to its mouth, so what they buy is its *depth* —
and unlike the pyramid it fills the canvas width, because a funnel that did not
would be a wedge in a corner.

The gates are drawn in the theme's `weak` edge role rather than as the shared
sides of separate polygons. A gate is a threshold, not a wall: the band is
continuous and something passes through it, which is what a stage boundary in a
funnel means and what a solid line would deny.

See `docs/reference/funnel-innovation.json`.

*Originals: `tic__gestion-de-la-innovacion-sgi__1`, `tic__soluciones-crm`.*

### And one that may not deserve a kind

`spans` — an axis of instants with nested labelled brackets over it (RPO, RTO,
WRT, MTD in the disaster-recovery diagram). One original. It is a real shape and
nothing draws it, but one is one; it may be better served by irregular timeline
spacing plus a bracket annotation than by a kind of its own.

### Out of scope, and worth saying so

Two originals are pictures: overlapping Wi-Fi cells, and one parcel of land drawn
vector against raster. They are illustrations of a physical thing, not diagrams
of a structure. **drawspec should not try to draw them** — a declarative document
whose author has no coordinates is the wrong tool for a picture, and pretending
otherwise is how a diagram language acquires an escape hatch that eats it.

---

## Features the covered ones still want

The 68 are drawable, but several want something the kind does not have yet. These
are cheaper than kinds and some are nearly free:

| Want | Where it shows | Kind |
|---|---|---|
| Emphasis on a node or an edge | the critical path marked through a network | flow |
| A label inside a bar | the five stars of open data, each in its own column | columns |
| A caption under the axis | *"depth of change in the organisation"* | timeline |
| Irregular spacing | events at their real intervals, not evenly | timeline |
| A dashed series, a label at the end of a line | ideal against real | chart |
| Bars, areas, stacked marks | not in the corpus, but the next thing asked for | chart |
| A fork and a join | components in series against in parallel | flow |
| Straight edges where the mesh *is* the message | spine-leaf, every leaf to every spine | flow |

That last one is worth its own sentence, because it contradicts a rule. The
review's rule 5.3 is *"right angles, not diagonals"*, and it is right: a diagonal
arriving at a box at a closed angle looks wrong, and orthogonal routing is why
drawspec's flow charts read cleanly. But in the spine-leaf diagram the twelve
straight diagonals **are** the content — "every leaf connects to every spine" is
legible as a lattice and illegible as twelve orthogonal routes threading a comb.
A rule that good still has an exception, and the exception should be a declared
edge style rather than a defeat.

---

## What this suggests doing first

1. ~~**`group`.**~~ Done — see above.
2. **Chart marks** — bars, areas, stacked. Not because the corpus demands them
   (it barely does) but because it is the standing request, and because the
   decision it forces — keep hand-rolling the chart or wrap an established
   library — gets more expensive with every mark type written by hand.
3. **`matrix`.** Five originals, and it is where the greyscale rule has to be
   made to work rather than merely obeyed.

`quadrant` and `curve` are each small and each self-contained; they can be
picked up in any order once the three above are settled. `funnel` is done.

---

## The inventory

Every original, the kind that would draw it, and the reviewer's note where
there is one. `*` marks a kind drawspec does not have.

| Original | Wants | Reviewer's note |
|---|---|---|
| `tic__pmbok-enfoques-y-ciclo-de-vida` | chart |  |
| `cataluna__estatut-autonomia-catalunya` | columns |  |
| `estado__funcion-publica-y-trebep` | columns | Margen inferior en cajas. "máxim 6 ANYS" está dentro del recuadro. Sin contexto no lo entiendo mucho, no sé si cada caja superior encaja con una inferior? |
| `tic__datos-abiertos-y-reutilizacion` | columns | Sólo la última queda con las estrellas encima del título. A lo mejor podrían ir todas así. |
| `tic__dominios-de-datos-data-mesh` | columns | Las cajas no están alineadas. Las de Domini sobresalen por la derecha. |
| `barcelona__scrum-bit` | *curve | Es un poco feo, pero no sé muy bien por qué. Lo de ideal y real está en sitios extraños. |
| `tic__pmbok-rendimiento-riesgos-y-cierre` | *curve | Es un gráfico muy raro, los textos se solapan, hay flechas con sólo punta, no hay texto para el eje vertical... Revisar entero. |
| `tic__prospeccion-de-soluciones-tic` | *curve | Puntos fuera de la línea y texto atravesando líneas. El texto "productivity\nPlateau of" queda cortado y creo que el texto esperado sería "Plateau of productivity". No quedan muy claros los ejes. |
| `barcelona__estrategia-municipal-de-algoritmos-y-datos` | cycle | "3. Contractació" (y todos en general) deberían ir centrados verticalmente? |
| `estado__haciendas-locales-y-presupuestos` | cycle | Fatal en cuanto a márgenes y flechas y texto que no cabe. Revisar completo. |
| `tic__automatizacion-orquestacion-y-rpa` | cycle | Centrado verticalmente. Sólo hay una flecha con cabeza, no sé si es lo esperado. |
| `tic__certificados-digitales-y-eidas` | cycle | Márgenes y no queda claro dónde van "Signant" y "Verificador" |
| `tic__gestion-de-incidentes-de-ciberseguridad` | cycle | Las flechas están todas mal. Como parece ser un ciclo, entiendo que tratan de simular un círculo, pero no aciertan. La frase "si hi ha indicis nous" queda cortada y no se ve entera, además de atravesar la línea. |
| `tic__gestion-de-la-innovacion-sgi__0` | cycle | Flechas sin palo. |
| `tic__gestion-del-riesgo-en-itil-v4` | cycle | Flechas con palo demasiado corto. |
| `tic__gestion-financiera-de-los-servicios` | cycle | Si trata de ser un ciclo, OK, pero las flechas cruzan líneas y las curvas son extrañas. Valorar ángulos de 90 grados. |
| `tic__medicion-y-mejora-continua` | cycle | Las flechas no acaban en la caja. |
| `barcelona__municipio-y-regimen-especial-de-barcelona` | flow | Creo que las frases deberían empezar en mayúscula. Además, estar centradas verticalmente. Y "Presideix la Commissió..." no cabe en la caja. |
| `barcelona__prevencion-de-riesgos-y-lengua-catalana` | flow | Puede que esté hecho a propósito, pero las flechas no tienen palo. Preferiría que lo tuvieran o bien que sean otro tipo de flechas. |
| `estado__administracion-electronica` | flow |  |
| `estado__administracion-general-del-estado` | flow | El texto de "Subdelegat del Govern" tiene interlineado irregular y no tiene margen inferior suficiente. |
| `estado__buen-gobierno` | flow | "Reclamació..." está debajo de todo y hay flechas que cruzan otras cajas. Si hace falta, haz el esquema vertical con flechas hacia abajo. |
| `estado__comunidades-autonomas` | flow | Margen inferior en "Competències...". |
| `estado__cortes-defensor-y-tribunal-de-cuentas` | flow | Mismo problema de líneas atravesando. Mejor esquema en vertical. Margen inferior en "Veto s'aixeca...". |
| `estado__el-gobierno` | flow | Flechas sin palo, Investit debería ir centrado verticalmente. Márgenes inferiores y texto que se sale. |
| `estado__poder-judicial` | flow |  |
| `tic__administracion-electronica-y-servicios-digitales` | flow | Triángulo raro en "Accés al contingut?". Texto que se solapa en "No, en 10 dies naturals". |
| `tic__analitica-de-datos-y-business-intelligence` | flow |  |
| `tic__arquitectura-de-microservicios` | flow | No sé de dónde debe salir la caja de "API Manager" |
| `tic__arquitecturas-de-seguridad-on-premise` | flow | Una flecha sin palo. |
| `tic__catalogo-de-servicios-y-sla` | flow | Líneas curvas extrañas, tratemos de hacerlas con ángulos y líneas rectas. |
| `tic__centros-de-proceso-de-datos` | flow | "Servidors..." quedan con el texto muy justo. |
| `tic__copias-de-seguridad-3-2-1-y-ransomware` | flow |  |
| `tic__gestion-centralizada-de-endpoints` | flow |  |
| `tic__gestion-de-capacidad-y-disponibilidad` | flow |  |
| `tic__gestion-de-datos-en-la-administracion` | flow | El subrayado de NIF (si es que hace falta) está muy pegado al texto. |
| `tic__gestion-de-identidades` | flow | Flechas curvas mejor con ángulos rectos. El texto de "1" se solapa. |
| `tic__gestion-de-la-demanda-tic` | flow | Flechas sin palo. |
| `tic__low-code-y-no-code` | flow |  |
| `tic__planificacion-estrategica-tic` | flow |  |
| `tic__plataforma-de-observabilidad` | flow | La letra es muy pequeña. |
| `tic__pmbok-gestion-del-trabajo` | flow |  |
| `tic__pmbok-planificacion-integrada` | flow | Líneas que no tocan cajas. Entiendo que "C" no está en negrita a propósito. |
| `tic__pmbok-valor-y-adaptacion` | flow | Texto muy pequeño. |
| `tic__rgpd` | flow |  |
| `tic__sap-basis-y-s4hana` | flow | "transport" queda tapado por la flecha las dos veces. Una de las flechas no tiene cabeza. |
| `tic__sap-fi-y-ea-ps` | flow |  |
| `tic__sap-hcm` | flow | Textos en cursiva se cruzan con flechas y cajas. |
| `tic__soluciones-erp` | flow |  |
| `tic__trabajo-colaborativo-microsoft-365` | flow | Aquí por ejemplo has usado líneas con ángulos rectos. Me gusta. Pero a diferencia del resto de los esquemas, las puntas de flecha no tocan las cajas de destino. |
| `tic__gestion-de-la-innovacion-sgi__1` | *funnel | Flechas sin palo. |
| `tic__soluciones-crm` | *funnel | Pirámide de forma rara. Texto "Compte i contacte" se solapa con las líneas (no cabe). |
| `estado__administracion-publica` | *group | Margen inferior e interlineado en b). |
| `tic__arquitectura-de-datos-dw-lake-lakehouse` | *group | "Ingesta" no cabe. "format" debería ser "Format"? Líneas entre las tres cajas principales con distinta longitud. |
| `tic__devops-cicd-contenedores-y-kubernetes` | *group | Comandos en monospace? |
| `tic__practicas-itil-de-entrega-de-servicios` | *group | La línea que sale de "Disseny del servei" va a "Transició del servei", mientras que la que llega a "Operació del servei" no viene de "Transició del servei" sino de un item interno, "Revisió posterior". Sólo comprobar si es correcto. La caja de debajo ("CMDB...") debería estar centrada con "Transició del servei o con todo el gráfico? Ahora no acaba de estar centrada del todo con nada. |
| `tic__practicas-itil-de-soporte-al-servicio` | *group | Yexto muy pequeño. Alguna flecha con poco palo. La palabra "excepció" no se sabe si es de la línea entre "Service Desk" y "Petició de servei" o de la línea entre "Esdeveniment" y "Incident" (o de las dos). |
| `tic__trabajo-documental-sharepoint-y-onedrive` | *group |  |
| `tic__arquitecturas-de-seguridad-en-la-nube` | *matrix | Las líneas de rayado son demasiado fuertes y cuesta leer "client". Además, hay como unos separadores entre las tres cajas que no se respetan ni por las líneas generales ni por el rayado. |
| `tic__computacion-hibrida-iaas-paas-saas` | *matrix | Mismo problema que antes en cuanto al rayado y las cajas separadas. A lo mejor "Gestiona el client" y "Gestiona el proveïdor" deberían ir al revés. |
| `tic__itil-v4-conceptos-y-cadena-de-valor` | *matrix | No acabo de entender este esquema: las líneas cruzan cajas, hay dos posibles flechas sin palo, el texto se sale de las cajas y es muy grande y en negrita (o con sombra, no sé). |
| `tic__sistemas-san-y-raid` | *matrix |  |
| `tic__tcp-ip-v4-y-mpls` | *matrix |  |
| `tic__redes-wifi` | *picture | Todos los AP quedan cruzados con el punto. La imagen queda cortada por abajo. El texto "solapament 15-20 %" no sé si está donde toca. Entiendo que el dibujo con los solapamientos sí es correcto. |
| `tic__servicios-digitales-geograficos` | *picture | Bello. Sólo el borde derecho del "Ràster" no ha quedado lo suficientemente gordo (o se sale de la imagen). |
| `barcelona__plan-de-igualdad-y-proteccion-de-datos` | pyramid | Irónicamente, cuanto más corto es el espacio, más largo es el texto. Si no cabe, puedes poner el 1 en dos líneas. |
| `estado__fuentes-del-derecho-publico` | pyramid |  |
| `tic__pruebas-de-software` | pyramid | Pirámide de forma extraña. |
| `tic__servicio-de-atencion-al-usuario` | pyramid | Pirámide de forma rara, texto pequeño. Revisar si el texto es correcto. |
| `tic__pmbok-liderazgo-equipo-y-recursos__0` | *quadrant | Puntas de flecha raras. |
| `tic__pmbok-liderazgo-equipo-y-recursos__1` | *quadrant | "Suavitzar / acomodar" atraviesa línea, y "Retirar / eludir" casi también. |
| `tic__aplicaciones-nativas-en-la-nube` | rings | Los textos de Cloud, Clúster y Contenidor deberían ir más abajo. Concretamente, Contenidor casi toca la línea. |
| `tic__gestion-documental-y-archivo-electronico` | rings |  |
| `tic__gobernanza-en-itil-v4` | rings | Textos que cruzan líneas. Posible falta de un círculo concéntrico. |
| `tic__inteligencia-artificial-riesgos-y-etica` | rings | Todos los textos atraviesan su propia línea.Valorar otro tipo de esquema o letra más pequeña, porque los textos son muy largos. |
| `tic__drp-y-bcp` | *spans |  |
| `estado__constitucion-espanola` | stack | A lo mejor un poco más de margen vertical. |
| `tic__brm-y-gestion-de-expectativas` | stack | Flechas un poco raras, no sé qué significan. |
| `tic__calidad-del-software` | stack |  |
| `tic__nube-soberana-y-administracion-publica` | stack |  |
| `tic__sap-trm` | stack | Flecha sin palo, márgenes inferiores escasos, entre las dos últimas cajas no hay texto... |
| `estado__acceso-al-empleo-publico` | timeline | Es raro partir una frase por cualquier lado y poner una parte con letra más pequeña. En el esquema siguiente tiene sentido, pero no aquí. Todo el texto debería ir arriba. No sé si a), b), c) y d) son necesarios, a no ser que vengan así en el texto. |
| `estado__acto-administrativo` | timeline |  |
| `tic__pmbok-interesadas-y-comunicacion` | timeline |  |
| `tic__transformacion-digital` | timeline |  |
| `barcelona__carta-municipal` | tree | Margen inferior en "Comissió de Govern". |
| `tic__despliegue-de-aplicaciones-sccm` | tree | Las líneas no tocan las cajas. |
| `tic__esquema-nacional-de-seguridad` | tree | Parece como si las líneas no llegaran a las cajas inferiores. |
| `tic__internet-arquitectura-protocolos-dns` | tree | El texto "13 conjunts..." toca líneas y cajas, no queda muy claro dónde debe ir. |
