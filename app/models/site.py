from sqlalchemy import Column, Integer, Text
from app.core.database import Base


class StagingMacro(Base):
    __tablename__ = "stg_ndpd_mbt_tmobile_macro_combined"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    s_site_id = Column(Text)
    pj_project_id = Column(Text)
    pj_project_name = Column(Text)
    m_market = Column(Text)
    m_area = Column(Text)
    region = Column(Text)
    pj_general_contractor = Column(Text)
    pj_hard_cost_vendor_assignment_po = Column(Text)
    por_plan_type = Column(Text)
    por_regional_dev_initiatives = Column(Text)
    construction_gc = Column(Text)

    # MS 3710
    pj_p_3710_ran_entitlement_complete_finish = Column(Text)
    pj_a_3710_ran_entitlement_complete_finish = Column(Text)

    # Pre-NTP
    ms_1310_pre_construction_package_received_actual = Column(Text)

    # Site Walk
    ms_1316_pre_con_site_walk_completed_actual = Column(Text)
    ms_1321_talon_view_drone_svcs_actual = Column(Text)

    # Scoping chain
    ms_1323_ready_for_scoping_actual = Column(Text)
    ms_1327_scoping_and_quoting_package_validated_actual = Column(Text)
    ms_1331_scoping_package_submitted_actual = Column(Text)

    # BOM
    pj_a_3850_bom_submitted_bom_in_bat_finish = Column(Text)
    pj_a_3875_bom_received_bom_in_aims_finish = Column(Text)

    # Steel
    pj_steel_received_date = Column(Text)
    pj_steel_received_status = Column(Text)

    # Material / Access / NTP
    pj_a_3925_msl_pickup_date_finish = Column(Text)
    pj_a_4000_ll_ntp_received = Column(Text)
    ms_1407_tower_ntp_validated_actual = Column(Text)

    # CPO / SPO
    ms1555_construction_complete_so_header = Column(Text)
    ms1555_construction_complete_spo_issued_date = Column(Text)

    # Construction start
    pj_p_4225_construction_start_finish = Column(Text)
