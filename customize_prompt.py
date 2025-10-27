def customize_prompts(prompts, app_info):
    """
    Enrich base prompts with both application-level and module-specific context.
    """

    # Module-specific enhancements
    module_context = {
        "login": "focus on user authentication, authorization, password reset flows, and session management.",
        "reporting": "include report generation workflows, data aggregation, scheduling, and export formats.",
        "data migration": "describe data extraction, transformation, validation, and load processes from old systems.",
        "dashboard": "cover KPIs, data visualization components, and role-based access to metrics.",
        "user management": "detail roles, permissions, user provisioning, and approval workflows.",
        "payment": "cover payment gateways, transaction validation, refund processes, and audit trails.",
        "notification": "include alerting logic, email/SMS templates, and event triggers."
    }

    customized_prompts = []
    for base_prompt in prompts:
        lower_p = base_prompt.lower()

        # Match to module context if possible
        matched_context = next((v for k, v in module_context.items() if k in lower_p), 
                               "include all functional and non-functional requirements.")

        # Build customized prompt
        customized = (
            f"{base_prompt} for the {app_info['name']} application. "
            f"This application uses {app_info['tech_stack']} (version {app_info['version']}). "
            f"Consider legacy aspects like {app_info['description']} and ensure BRD covers backward compatibility. "
            f"Specifically, {matched_context}"
        )

        customized_prompts.append(customized)

    return customized_prompts


# Example usage
prompts = [
    "Generate BRD for the login module",
    "Generate BRD for the reporting module",
    "Generate BRD for the data migration process",
    "Generate BRD for the dashboard view"
]

app_info = {
    "name": "Legacy HRMS",
    "description": "existing employee, payroll, and attendance workflows built on older monolithic architecture.",
    "version": "v3.2",
    "tech_stack": "Java, Oracle DB, and JSP frontend"
}

final_prompts = customize_prompts(prompts, app_info)

for i, p in enumerate(final_prompts, 1):
    print(f"{i}. {p}\n")
