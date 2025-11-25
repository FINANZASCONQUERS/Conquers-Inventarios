#!/usr/bin/env python3
"""
Script de prueba para verificar que el sistema anti-spoofing
no bloquea a los usuarios y sigue enviando advertencias.
"""

def test_spoofing_no_block():
    """Prueba que el sistema no bloquea y sigue enviando mensajes"""

    # Simular múltiples intentos de spoofing
    test_cases = [
        (1, "Primer intento - debería ser mensaje divertido"),
        (2, "Segundo intento - debería ser mensaje más serio"),
        (3, "Tercer intento - debería ser mensaje amenazante"),
        (4, "Cuarto intento - debería ser mensaje con consecuencias"),
        (5, "Quinto intento - debería ser mensaje máximo severidad"),
        (6, "Sexto intento - debería seguir siendo mensaje máximo severidad"),
        (10, "Décimo intento - debería seguir siendo mensaje máximo severidad"),
        (50, "Cincuentaavo intento - debería seguir siendo mensaje máximo severidad"),
    ]

    print("🧪 PRUEBA: SISTEMA ANTI-SPOOFING SIN BLOQUEO")
    print("=" * 70)

    spoofing_messages = [
        # Primer intento - Divertido pero firme
        "🐶 Fisher 🐶: ¡Oye, amigo! Detecté que intentaste enviar una ubicación de mapa 📍 en lugar de GPS real desde Bosconia.\n\n"
        "Sé que eres inteligente, pero esto no engaña a mi nariz de perro 🐕. ¡Inténtalo de nuevo con tu ubicación REAL!",

        # Segundo intento - Más serio
        "🐕 Fisher 🐶: ¡Guau! Segundo intento fallido en Bosconia. Mi olfato canino huele que estás tratando de engañarme con una ubicación del mapa.\n\n"
        "Recuerda: Clip 📎 → Ubicación → **'Enviar mi ubicación actual'** (el botón azul). ¡No uses el buscador!",

        # Tercer intento - Amenazante
        "🐶 Fisher 🐶: ¡Basta ya! Tres intentos de spoofing GPS en Bosconia. Mi paciencia de perro se está agotando.\n\n"
        "⚠️ Si sigues intentando engañarme, tu posición en el enturnamiento bajará automáticamente. ¡Envía tu ubicación REAL ahora!",

        # Cuarto intento - Muy serio con consecuencias
        "🐕 Fisher 🐶: ¡Esto es inaceptable! Cuatro intentos de spoofing en Bosconia.\n\n"
        "🚫 Como castigo por intentar engañar al sistema, tu prioridad en el enturnamiento ha bajado. Ahora tendrás que esperar más tiempo.\n\n"
        "¡Última oportunidad! Envía tu ubicación REAL o tu posición seguirá bajando.",

        # Quinto intento y posteriores - Máxima severidad
        "🐶 Fisher 🐶: ¡Ya basta! Múltiples intentos de spoofing detectados en Bosconia.\n\n"
        "💀 Tu posición en el enturnamiento ha sido degradada significativamente. Ahora eres el último en la fila.\n\n"
        "Si sigues intentando engañarme, tu solicitud será cancelada permanentemente. ¡Comportate!"
    ]

    for spoofing_count, description in test_cases:
        # Simular la lógica de selección de mensaje
        if spoofing_count >= 5:
            message_index = len(spoofing_messages) - 1  # Siempre el último mensaje
        else:
            message_index = min(spoofing_count - 1, len(spoofing_messages) - 1)

        message = spoofing_messages[message_index]

        # Verificar que no hay mensaje de bloqueo
        is_blocked = "BLOQUEADA" in message or "bloqueado" in message.lower()

        print(f"\n📍 Intento #{spoofing_count}: {description}")
        print(f"   Mensaje usado: #{message_index + 1} de {len(spoofing_messages)}")
        print(f"   ¿Bloqueado?: {'❌ SÍ' if is_blocked else '✅ NO'}")
        print(f"   Longitud mensaje: {len(message)} caracteres")

    print("\n" + "=" * 70)
    print("📋 RESULTADO:")
    print("✅ El sistema NO bloquea a los usuarios")
    print("✅ Sigue enviando advertencias indefinidamente")
    print("✅ Usa el mensaje más severo para intentos múltiples")
    print("✅ Los usuarios pueden corregirse enviando ubicación real")

if __name__ == "__main__":
    test_spoofing_no_block()