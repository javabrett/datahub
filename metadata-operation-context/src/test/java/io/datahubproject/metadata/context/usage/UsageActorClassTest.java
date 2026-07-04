package io.datahubproject.metadata.context.usage;

import com.linkedin.metadata.Constants;
import org.testng.Assert;
import org.testng.annotations.Test;

public class UsageActorClassTest {

  @Test
  public void testFromActorUrnSystem() {
    Assert.assertEquals(
        UsageActorClass.fromActorUrn(Constants.SYSTEM_ACTOR), UsageActorClass.SYSTEM);
    Assert.assertEquals(
        UsageActorClass.fromActorUrn(Constants.SYSTEM_ACTOR).toLegacyUserCategoryTag(), "system");
  }

  @Test
  public void testFromActorUrnSupportBuiltIns() {
    Assert.assertEquals(
        UsageActorClass.fromActorUrn(Constants.DATAHUB_ACTOR), UsageActorClass.SUPPORT);
    Assert.assertEquals(
        UsageActorClass.fromActorUrn(Constants.DATAHUB_ACTOR).toLegacyUserCategoryTag(), "support");
    Assert.assertEquals(
        UsageActorClass.fromActorUrn(Constants.ADMIN_ACTOR), UsageActorClass.SUPPORT);
  }

  @Test
  public void testFromActorUrnRegular() {
    Assert.assertEquals(
        UsageActorClass.fromActorUrn("urn:li:corpuser:test"), UsageActorClass.REGULAR);
    Assert.assertEquals(
        UsageActorClass.fromActorUrn("urn:li:corpuser:test").toLegacyUserCategoryTag(), "regular");
  }

  @Test
  public void testDimensionValue() {
    Assert.assertEquals(UsageActorClass.REGULAR.dimensionValue(), "regular");
    Assert.assertEquals(UsageActorClass.SYSTEM.dimensionValue(), "system");
    Assert.assertEquals(UsageActorClass.SUPPORT.dimensionValue(), "support");
  }
}
