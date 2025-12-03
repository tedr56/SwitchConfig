from ansible.module_utils.basic import AnsibleModule
import re
import time

# Base de prompts par marque
PROMPTS_BY_BRAND = {
    "cisco": {
        "EXEC user": r">\s*$",
        "EXEC privileged": r"#\s*$",
        "Configuration": r"\(config.*\)#\s*$",
    },
    "juniper": {
        "Operational": r">%$",
        "Configuration": r"#\s*$",
    },
    "hp_aruba": {
        "EXEC user": r">\s*$",
        "EXEC privileged": r"#\s*$",
        "Configuration": r"\(config.*\)#\s*$",
    },
}

def detect_prompt(output, prompt_patterns):
    """
    Détecte le prompt à partir des motifs fournis.
    """
    for prompt_name, pattern in prompt_patterns.items():
        if re.search(pattern, output):
            return prompt_name
    return None

def wait_for_prompt(ser, prompt_patterns, wait_timeout, poll_interval=1):
    """
    Attend le prompt attendu jusqu'à un délai maximum.
    - ser : Objet série (serial.Serial).
    - prompt_patterns : Dictionnaire des prompts à rechercher.
    - wait_timeout : Temps maximum en secondes.
    - poll_interval : Intervalle entre les lectures.
    """
    start_time = time.time()
    buffer = ""

    while time.time() - start_time < wait_timeout:
        if ser.in_waiting > 0:  # Vérifie s'il y a des données disponibles
            buffer += ser.read(ser.in_waiting).decode("utf-8")
            detected_prompt = detect_prompt(buffer, prompt_patterns)
            if detected_prompt:
                return detected_prompt, buffer
        else:
            time.sleep(poll_interval)  # Attendre avant de relire

    return None, buffer

def run_module():
    module_args = dict(
        port=dict(type='str', required=True),  # Port série (ex. /dev/ttyUSB0)
        command=dict(type='str', required=True),  # Commande à exécuter
        baudrate=dict(type='int', required=False, default=9600),  # Baudrate
        brand=dict(type='str', required=False, default=None),  # Marque du switch (ex. cisco)
        prompt_patterns=dict(type='dict', required=False, default=None),  # Prompts spécifiques
        target_mode=dict(type='str', required=True),  # Mode cible (ex. EXEC privileged)
        wait_timeout=dict(type='int', required=False, default=60),  # Temps maximum pour attendre le prompt
        timeout=dict(type='int', required=False, default=5),  # Timeout pour lire la réponse
    )
    result = dict(
        changed=False,
        detected_prompt='',
        output=''
    )

    module = AnsibleModule(argument_spec=module_args)

    # Paramètres
    port = module.params['port']
    command = module.params['command']
    baudrate = module.params['baudrate']
    brand = module.params['brand']
    custom_prompts = module.params['prompt_patterns']
    target_mode = module.params['target_mode']
    wait_timeout = module.params['wait_timeout']
    timeout = module.params['timeout']

    # Déterminer les prompts à utiliser
    if brand:
        prompt_patterns = PROMPTS_BY_BRAND.get(brand.lower())
        if not prompt_patterns:
            module.fail_json(msg=f"La marque '{brand}' n'est pas supportée. Fournissez des 'prompt_patterns' personnalisés.")
    elif custom_prompts:
        prompt_patterns = custom_prompts
    else:
        module.fail_json(msg="Vous devez spécifier une marque connue ou fournir des 'prompt_patterns' personnalisés.")

    # Vérification du mode cible dans les prompts
    if target_mode not in prompt_patterns:
        module.fail_json(msg=f"Le mode cible '{target_mode}' n'existe pas dans les prompts fournis.")

    try:
        # Étape 1 : Connexion série
        import serial
        ser = serial.Serial(port, baudrate, timeout=timeout)
        ser.write(b'\r\n')  # Envoyer un retour chariot pour activer le prompt

        # Étape 2 : Attente du prompt
        detected_prompt, buffer = wait_for_prompt(ser, prompt_patterns, wait_timeout)
        result['detected_prompt'] = detected_prompt
        result['output'] = buffer

        if not detected_prompt:
            ser.close()
            module.fail_json(msg="Timeout atteint sans détecter de prompt.", **result)

        # Étape 3 : Navigation entre les modes (si nécessaire)
        if detected_prompt != target_mode:
            if target_mode == 'EXEC privileged' and detected_prompt == 'EXEC user':
                ser.write(b'enable\r\n')
                buffer += ser.read(1024).decode('utf-8')  # Lire la sortie pour voir si un mot de passe est demandé
                if re.search(r'Password:', buffer):
                    ser.close()
                    module.fail_json(msg="Le mot de passe est requis pour entrer en mode privilégié")

            # Ajouter ici d'autres transitions entre les modes si nécessaire

        # Étape 4 : Envoi de la commande
        ser.write((command + '\r\n').encode('utf-8'))
        buffer += ser.read(1024).decode('utf-8')
        ser.close()

        result['output'] = buffer
        module.exit_json(**result)

    except Exception as e:
        module.fail_json(msg=str(e))

def main():
    run_module()

if __name__ == '__main__':
    main()
