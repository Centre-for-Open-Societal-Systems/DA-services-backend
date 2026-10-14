#!/usr/bin/env python3
"""Fix DA RBAC Assignment module in database."""

import frappe

def main():
    frappe.init(site='da-services.localhost')
    frappe.connect()

    # Update module
    frappe.db.sql("""
        UPDATE tabDocType
        SET module = 'DA Services'
        WHERE name = 'DA RBAC Assignment'
    """)
    frappe.db.commit()

    # Verify
    result = frappe.db.sql("""
        SELECT name, module
        FROM tabDocType
        WHERE name IN ('DA RBAC Assignment', 'DA Farmer Reference', 'DA Farmer Link')
    """, as_dict=True)

    print("DocType modules:")
    for row in result:
        print(f"  {row.name}: {row.module}")

    frappe.destroy()

if __name__ == "__main__":
    main()
