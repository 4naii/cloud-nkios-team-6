"""API 입력/출력 형식 정의 (잘못된 값은 FastAPI가 자동으로 422 에러 반환)"""
from typing import Literal

from pydantic import BaseModel, Field

Workclass = Literal["Private", "Self-emp-not-inc", "Self-emp-inc", "Federal-gov", "Local-gov",
                    "State-gov", "Without-pay", "Never-worked", "Unknown"]
Marital = Literal["Married-civ-spouse", "Never-married", "Divorced", "Separated", "Widowed",
                  "Married-spouse-absent", "Married-AF-spouse"]
Occupation = Literal["Adm-clerical", "Armed-Forces", "Craft-repair", "Exec-managerial",
                     "Farming-fishing", "Handlers-cleaners", "Machine-op-inspct", "Other-service",
                     "Priv-house-serv", "Prof-specialty", "Protective-serv", "Sales",
                     "Tech-support", "Transport-moving", "Unknown"]
Relationship = Literal["Husband", "Wife", "Own-child", "Not-in-family", "Other-relative", "Unmarried"]
Race = Literal["White", "Black", "Asian-Pac-Islander", "Amer-Indian-Eskimo", "Other"]
Sex = Literal["Male", "Female"]


class PersonIn(BaseModel):
    age: int = Field(..., ge=17, le=90, examples=[39])
    workclass: Workclass = Field("Private")
    education_num: int = Field(..., ge=1, le=16, description="학력 1~16 (13=학사, 14=석사, 16=박사)",
                               examples=[13])
    marital_status: Marital
    occupation: Occupation
    relationship: Relationship
    race: Race
    sex: Sex
    capital_gain: float = Field(0, ge=0, le=99999)
    capital_loss: float = Field(0, ge=0, le=4356)
    hours_per_week: int = Field(..., ge=1, le=99, examples=[40])
    native_country: str = Field("United-States", description="미국 외 국가는 모두 'Other'로 처리됨")


class PredictionOut(BaseModel):
    prediction: int = Field(..., description="1 = >50K, 0 = <=50K")
    label: str
    probability: float = Field(..., description=">50K일 확률")
    threshold: float
