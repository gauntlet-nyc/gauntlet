# Evaluator-only benchmark truth

The directory is *not* a valid security boundary by itself. Store true hidden exploit cases and evaluator answer keys in a separate repository, mounted volume or secret artifact store that **cannot be accessed by the planner, repository analyzer, attacker, fixer or demo target**. No private truth files are shipped with this starter. Merely adding them to `.gitignore` would not prevent an attacker from reading them through Git history or adjacent mounts.
