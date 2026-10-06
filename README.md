<div align="center">
  <h1>PipoLauncher - Informacion general</h1>
  <img src="resources/head.png" alt="PipoLauncher">
</div>

<br>

PipoLauncher es un proyecto independiente creado con fines educativos y de utilidad personal. Este software no está afiliado, respaldado, asociado ni patrocinado por Mojang AB, Microsoft Corporation ni ninguna de sus filiales. 'Minecraft' es una marca comercial de Mojang Synergies AB. Se recomienda a todos los usuarios adquirir una copia oficial del juego para apoyar a los desarrolladores.

Las partes marcadas como _(verificado)_ salen del propio código del Launcher. Las marcadas como _(orientativo)_ son estimaciones de uso general, no cifras oficiales.

SISTEMA OPERATIVO  -  (verificado)
----------------------------------
■	Windows 10 u 11, 64 bits.   OBLIGATORIO

Motivo: el launcher usa funciones propias de Windows (lectura de la memoria del equipo, lanzamiento de procesos) y descarga los componentes de Java y las librerías nativas para "windows-x64". Las versiones recientes de Minecraft usan Java 21 o 25, que también piden Windows 10 o superior.

Aun no se ha probado el launcher en: macOS, Linux, Windows de 32 bits ni Windows en equipos ARM.

HARDWARE PARA JUGAR - (fuente: Mojang, página actualizada el 21/07/2026)
------------------------------------------------------------------------
El launcher en sí consume muy poco. Lo que pesa es Minecraft, y sus requisitos dependen de la versión que elijas.

VERSIONES ACTUALES de Minecraft: Java Edition (mínimos publicados por Mojang, para 1080p a 30 FPS con el preset "Fast"):

■	Sistema de 64 bits

■	RAM: 8 GB con tarjeta gráfica dedicada, o 12 GB si usás gráficos integrados

■	Procesador de 4 núcleos

■	GPU compatible con Vulkan 1.3 y al menos 2 GB de VRAM

Recomendado por Mojang (1080p a 60 FPS con el preset "Fancy"):

■	  16 GB de RAM

■	GPU más potente, con 6 GB de VRAM

■	Un procesador moderno y más fuerte

Mojang avisa que el juego está pasando de OpenGL a Vulkan, y que en hardware por debajo de esos mínimos el rendimiento no está garantizado y en el futuro podría no iniciar.

VERSIONES ANTERIORES: piden bastante menos. Con 4 GB
de RAM, un procesador de 2 núcleos o más y una GPU integrada reciente con los controladores al día, suelen andar. Las más viejas (1.8, 1.12, etc.) funcionan incluso en equipos más modestos.

MEMORIA RAM QUE PUEDE ASIGNAR EL LAUNCHER  -  (verificado)
----------------------------------------------------------
Al juego se le puede dar toda la RAM del equipo MENOS una reserva para Windows: lo mayor entre 2 GB y el 25 % del total.

       RAM del equipo  ->  Máximo asignable
             4 GB      ->        2 GB
             8 GB      ->        6 GB
            16 GB      ->       12 GB
            32 GB      ->       24 GB

Esto se puede cambiar en el engranaje, arriba a la derecha.

ESPACIO EN DISCO  -  (orientativo)
----------------------------------
Todo se guarda en:  %APPDATA%\.minecraft (la configuración y los logs, en la subcarpeta Pipolauncher)

■	Launcher, configuración y logs: unos pocos MB.

■	Java: se instala por separado cada runtime (8, 16, 17, 21, 25). En el primer inicio se instalan todos: unos 1 GB en total, aproximadamente.

■	Cada versión de Minecraft: el juego (~20-30 MB) más sus librerías. Los recursos (sonidos, idiomas, texturas) se comparten entre versiones y pueden llegar a varios cientos de MB).

  Recomendado: al menos 5 GB libres para empezar y 10 GB o más si
  vas a instalar muchas versiones. Un SSD acelera mucho la carga.
  
CONEXIÓN A INTERNET  -  (verificado)
------------------------------------
■	Hace falta para el primer inicio y para descargar versiones marcadas con [+].

■	Para jugar versiones ya instaladas NO hace falta: el launcher usa la última lista de versiones guardada.

■	Se recomienda una conexión de 10 Mbps o más para las descargas.

■	Si un firewall, proxy o antivirus bloquea las descargas, hay que permitir el acceso HTTPS (puerto 443) a estos dominios de Mojang. Los tres primeros están escritos en el launcher; los otros dos son los que suelen usar las listas de Mojang para el juego y las librerías, y pueden cambiar con el tiempo:

         		piston-meta.mojang.com
         		launchermeta.mojang.com
         		resources.download.minecraft.net
         		piston-data.mojang.com
         		libraries.minecraft.net

Para abrir el enlace del logo se necesita un navegador instalado y configurado como predeterminado en Windows.

OTROS DETALLES
--------------
■	No necesita permisos de administrador (escribe solo en su carpeta de usuario).

■	Pantalla: la ventana mide 800 x 450. Cualquier resolución desde 1024 x 768 sirve. Con el escalado de Windows alto (150 % o más), la ventana se verá proporcionalmente más grande.

■	Modo de juego: sin cuenta Microsoft (el nombre es libre). Los servidores con verificación de cuenta oficial no aceptan este modo.

■	Si el antivirus marca el .exe, suele ser un falso positivo común en programas empaquetados; hay que agregarlo como excepción.




Fuente de los requisitos de hardware de Minecraft:

https://minecraft.net/en-us/article/minecraft-java-edition-system-requirements
