LASERJOIN STUDIO WEB MOBILE v1
===============================

QUÉ CAMBIA
==========
Esta versión se usa desde el navegador del celular o de la PC.

Regla de encastre:
- Pestaña macho = espesor del MDF.
- Hueco hembra = espesor del MDF - diferencia.

Ejemplo:
MDF: 3.00 mm
Diferencia: 0.01 mm

Resultado:
Pestaña = 3.00 mm
Hueco = 2.99 mm

La diferencia es editable desde la app.

INSTALACIÓN EN LA PC
====================
1. Doble clic en INSTALAR_DEPENDENCIAS.bat
2. Cuando termine, doble clic en ABRIR_APP.bat

La ventana negra mostrará dos direcciones.

En la PC:
http://127.0.0.1:5000

En el celular:
http://IP-DE-TU-PC:5000

IMPORTANTE:
- PC y celular deben estar conectados a la misma red Wi-Fi.
- Dejá ABRIR_APP.bat abierto mientras uses la app desde el celular.
- Si Windows pregunta si permitís acceso en redes privadas, permitilo para tu red privada.

EXPORTACIÓN
===========
El botón "DESCARGAR 3DM + DXF" baja un ZIP con:
- laserjoin_box_mobile.3dm
- laserjoin_box_mobile.dxf

El archivo 3DM está en milímetros y se puede abrir en Rhino 7/8.

AGREGAR COMO APP EN ANDROID
===========================
En Chrome:
1. Abrí LaserJoin Studio.
2. Menú ⋮.
3. "Agregar a pantalla principal" o "Instalar app" si aparece.

LIMITACIÓN ACTUAL
=================
El kerf queda editable, pero todavía no se aplica automáticamente a la geometría.
Antes del corte final, calibrá con una probeta real del mismo MDF y la misma cortadora.
